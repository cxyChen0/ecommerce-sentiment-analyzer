import requests
import re
import json
from fake_useragent import UserAgent
import csv
import hashlib
import time
import random
import chardet

# 精准屏蔽无关警告，不影响真正错误
import warnings
from requests.exceptions import RequestsDependencyWarning
warnings.filterwarnings("ignore", category=RequestsDependencyWarning)

def get_file_encoding(file_path):
    with open(file_path, 'rb') as f:
        result = chardet.detect(f.read())
    return result['encoding']

# 文件名后缀
suffix = "snakes5"

# 读取商品ID列表
def read_goods_ids():
    goods = []
    file_path = f'data_{suffix}.csv'

    # 自动检测编码
    encoding = get_file_encoding(file_path)
    print(f"自动检测文件编码：{encoding}")
    with open(file_path, 'r', encoding=encoding, errors='ignore') as f:
        reader = csv.DictReader(f)
        for row in reader:
            sales_str = str(row.get('销量', '')).strip()
            sales_num = 0

            # 支持：1.2万、3.5万、2万、6000+、0人付款
            if '万' in sales_str:
                match = re.search(r'(\d+\.?\d*)万', sales_str)
                if match:
                    sales_num = int(float(match.group(1)) * 10000)
            else:
                match = re.search(r'(\d+)', sales_str)
                if match:
                    sales_num = int(match.group(1))

            # 过滤 < 10
            if sales_num >= 10:
                goods.append(row['商品ID'])

    return goods

goods_ids = read_goods_ids()
print(f"待爬取商品总数：{len(goods_ids)}")

def get_token_from_cookie(cookie):
    for item in cookie.split(";"):
        if "_m_h5_tk=" in item:
            return item.split("=")[-1].split("_")[0]
    return ""

f = open(file=f'content_{suffix}.csv', mode='w', encoding='utf-8-sig', newline='')
csv_writer = csv.DictWriter(f, fieldnames=['商品ID','商品名称','评论'])
csv_writer.writeheader()

ua = UserAgent()

# ====================
# 【重要】完整请求头，大幅降低风控
# ====================
headers = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    'accept-encoding': 'gzip, deflate, br',
    'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'cache-control': 'max-age=0',
    'connection': 'keep-alive',
    'sec-ch-ua': '"Not_A Brand";v="99", "Google Chrome";v="99", "Chromium";v="99"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'document',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-site': 'none',
    'sec-fetch-user': '?1',
    'upgrade-insecure-requests': '1',
    'user-agent': ua.random,
    'referer': 'https://detail.tmall.com/',
    'cookie': '',
}

token = get_token_from_cookie(headers['cookie'])

def getSign(c, pageNum, goods_id):
    r = token
    u = '12574478'
    n_data = '{"showTrueCount":false,"auctionNumId":"%s","pageNo":%d,"pageSize":20,"orderType":"","searchImpr":"-8","expression":"","skuVids":"","rateSrc":"pc_rate_list","rateType":"","foldFlag":"0"}' % (goods_id, pageNum)
    string = r + "&" + str(c) + "&" + u + "&" + n_data
    MD5 = hashlib.md5()
    MD5.update(string.encode('utf-8'))
    sign = MD5.hexdigest()
    return sign

# ======================
# 主爬取逻辑
# ======================
for goods_id in goods_ids:
    print("\n======================================")
    print(f"正在爬取商品：{goods_id}")

    # ✅ 每个商品【开始前】更换 UA（正确位置）
    headers["user-agent"] = ua.random
    time.sleep(random.uniform(1, 2))

    for page in range(1, 6):
        print(f"\n📄 正在采集第{page}页")
        c = int(time.time() * 1000)
        sign = getSign(c=c, pageNum=page, goods_id=goods_id)
        url = 'https://h5api.m.tmall.com/h5/mtop.taobao.rate.detaillist.get/6.0/'

        data = {
            'jsv':'2.7.5','appKey':'12574478','t':c,'sign':sign,
            '_bx-login':'new','api':'mtop.taobao.rate.detaillist.get','v':'6.0',
            'isSec':'0','ecode':'1','timeout':'20000',
            'dataType':'jsonp','valueType':'string','type':'jsonp',
            'callback':'mtopjsonp%d' % random.randint(10, 50),
            'data':'{"showTrueCount":false,"auctionNumId":"%s","pageNo":%d,"pageSize":20,"orderType":"","searchImpr":"-8","expression":"","skuVids":"","rateSrc":"pc_rate_list","rateType":"","foldFlag":"0"}' % (goods_id, page),
        }

        try:
            response = requests.get(url=url, params=data, headers=headers, timeout=12)
            text = response.text
            match = re.search(r'mtopjsonp\d+\((.*?)\)$', text)

            if not match:
                print("❌ 未获取到数据，可能被风控，休息30秒")
                time.sleep(30)
                continue

            info = match.group(1)
            json_data = json.loads(info)

            # ====================
            # 风控/限流检测
            # ====================
            if "ret" in json_data:
                ret_str = str(json_data["ret"])

                # Cookie 失效
                if any(k in ret_str for k in ["非法请求","未登录","token过期","fail_sys"]):
                    print("\n❌ Cookie 已过期！")
                    f.close()
                    exit()

                # 淘宝限流：哎哟喂被挤爆啦
                if "RGV587_ERROR" in ret_str or "哎哟喂" in ret_str:
                    print("⚠️ 触发限流！")
                    f.close()
                    exit()

            # 无数据判断
            if 'data' not in json_data or 'rateList' not in json_data['data']:
                print("❌ 无评论数据或被风控")
                f.close()
                exit()

            rateList = json_data['data']['rateList']
            if len(rateList) == 0:
                print(f"✅ 第{page}页无评论，结束此商品")
                break

            # 写入数据
            for index in rateList:
                dit = {
                    '商品ID': index['auctionNumId'],
                    '商品名称': index['auctionTitle'],
                    '评论': index['feedback'],
                }
                csv_writer.writerow(dit)
            print(f"✅ 第{page}页采集完成")

        except Exception as e:
            print("❌ 页面异常，跳过:", e)
            time.sleep(20)
            continue

        # 页面间隔（真人速度）
        time.sleep(random.uniform(7, 9))

    # 商品结束后长休息
    time.sleep(random.uniform(12, 15))

f.close()
print("\n🎉 全部爬取完成！")