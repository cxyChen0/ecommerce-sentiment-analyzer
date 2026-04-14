import requests
import re
import json
from fake_useragent import UserAgent
import csv
import hashlib
import time
import random
import chardet

def get_file_encoding(file_path):
    with open(file_path, 'rb') as f:
        result = chardet.detect(f.read())
    return result['encoding']

# 文件名后缀
suffix = "snakes8"


# 获取已经爬取的最后一个商品ID
def get_last_crawled_id():
    try:
        with open(f'content_{suffix}.csv', 'r', encoding='utf-8-sig') as f:
            lines = f.readlines()
            if len(lines) <= 1:
                return None
            last_line = lines[-1].strip()
            return last_line.split(',')[0]  # 第一列就是商品ID
    except:
        return None

# 读取商品ID列表
def read_goods_ids():
    goods = []
    file_path = f'data_{suffix}.csv'

    # 自动检测编码
    encoding = get_file_encoding(file_path)
    print(f"自动检测文件编码：{encoding}")
    with open(file_path, 'r', encoding=encoding) as f:
        reader = csv.DictReader(f)
        for row in reader:
            sales_str = str(row.get('销量', '')).strip()
            sales_num = 0

            # 支持：1.2万、3.5万、2万、6000+、0人付款
            if '万' in sales_str:
                # 提取小数/整数 + 万
                match = re.search(r'(\d+\.?\d*)万', sales_str)
                if match:
                    sales_num = int(float(match.group(1)) * 10000)
            else:
                # 提取普通数字
                match = re.search(r'(\d+)', sales_str)
                if match:
                    sales_num = int(match.group(1))

            # 过滤 < 10
            if sales_num >= 10:
                goods.append(row['商品ID'])

    return goods

goods_ids = read_goods_ids()  # 读取所有商品ID
last_id = get_last_crawled_id()
if last_id:
    print(f"继续爬取，上次最后ID：{last_id}")
    if last_id in goods_ids:
        idx = goods_ids.index(last_id)
        goods_ids = goods_ids[idx+1:]  # 从下一个开始

def get_token_from_cookie(cookie):
    for item in cookie.split(";"):
        if "_m_h5_tk=" in item:
            return item.split("=")[-1].split("_")[0]
    return ""


# 追加模式，不会覆盖！
f = open(file=f'content_{suffix}.csv', mode='a+', encoding='utf-8-sig', newline='')
csv_writer = csv.DictWriter(f, fieldnames=[
    '商品ID',
    '商品名称',
    '评论',
])

# 只有文件为空时才写表头（避免追加时重复写表头）
f.seek(0)
if not f.read(1):
    csv_writer.writeheader()

ua = UserAgent()

headers = {
    # 用户信息, 常用于检测是否有登陆账号
    'cookie': '',
    # 用户代理, 表示浏览器/设备的基本身份信息
    "user-agent": ua.random,
    "referer": "https://detail.tmall.com/",
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
    print(sign)
    return sign

for goods_id in goods_ids:
    print("正在爬取商品", goods_id)

    total_page = random.randint(3, 6)
    for page in range(1, total_page + 1):
        print(f'正在采集第{page}页的数据内容')
        c = int(time.time() * 1000)
        sign = getSign(c=c, pageNum=page, goods_id=goods_id)
        url = 'https://h5api.m.tmall.com/h5/mtop.taobao.rate.detaillist.get/6.0/'

        data = {
        'jsv':'2.7.5',
        'appKey':'12574478',
        't':c,
        'sign':sign,
        '_bx-login':'new',
        'api':'mtop.taobao.rate.detaillist.get',
        'v':'6.0',
        'isSec':'0',
        'ecode':'1',
        'timeout':'20000',
        'dataType':'jsonp',
        'valueType':'string',
        'type':'jsonp',
        'callback':'mtopjsonp%d' % random.randint(10, 50),
        'data':'{"showTrueCount":false,"auctionNumId":"%s","pageNo":%d,"pageSize":20,"orderType":"","searchImpr":"-8","expression":"","skuVids":"","rateSrc":"pc_rate_list","rateType":"","foldFlag":"0"}' % (goods_id, page),
        }

        try:
            response = requests.get(url=url, params=data, headers=headers, timeout=10)
            text = response.text
            match = re.search(r'mtopjsonp\d+\((.*?)\)$', text)
            if not match:
                print("❌ 未获取到数据，可能被风控")
                time.sleep(10)
                continue

            info = match.group(1)
            json_data = json.loads(info)

            if "ret" in json_data:
                ret_str = str(json_data["ret"]).lower()

                # 只要出现这些关键词 = Cookie 失效
                if any(key in ret_str for key in [
                    "非法请求", "无效请求", "非法访问",
                    "token过期", "未登录", "fail_sys"
                ]):
                    print("\n" + "=" * 60)
                    print("❌ 【严重】Cookie 已过期！！！")
                    print("请重新去浏览器复制最新 Cookie！")
                    print("=" * 60 + "\n")

                    # 关闭文件并退出，避免数据损坏
                    f.close()
                    exit()

            # 淘宝限流：哎哟喂被挤爆啦
            if "RGV587_ERROR" in ret_str or "哎哟喂" in ret_str:
                print("⚠️ 触发限流！")
                f.close()
                exit()

            # 检查是否返回正常
            if 'data' not in json_data or 'rateList' not in json_data['data']:
                print("❌ 无评论数据或被风控", json_data.get('ret'))
                f.close()
                exit()

            rateList = json_data['data']['rateList']
            # 如果这一页没有评论，说明后面都没有了，直接跳出翻页循环
            if len(rateList) == 0:
                print(f"✅ 第{page}页无评论，此商品后续页不再爬取")
                break

        except Exception as e:
            print("❌ 页面异常，跳过:", e)
            time.sleep(10)
            continue

        for index in rateList:
            dit = {
                '商品ID' : goods_id,
                '商品名称' : index['auctionTitle'],
                '评论' : index['feedback'],
            }
            csv_writer.writerow(dit)
            print(dit)

        time.sleep(random.uniform(5, 8))

    # 每个商品换一次UA
    headers["user-agent"] = ua.random
    # 商品之间休息 8-12 秒
    time.sleep(random.uniform(8, 12))


f.close()