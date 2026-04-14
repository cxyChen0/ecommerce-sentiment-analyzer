"""发送请求"""
import requests
import json
import hashlib
import time
import re
import csv

f = open('data.csv', mode='w', encoding='utf-8', newline='')
csv_writer = csv.DictWriter(f, fieldnames=[
    '标题',
    '店铺',
    '价格',
    '省份',
    '城市',
    '销量',
    '商品ID',
    '商品链接',
])
# 写入表头
csv_writer.writeheader()

"""获取sign加密参数"""
token = "31ad091fe704130200cef3fa056456a9"
eT = int(time.time() * 1000)
eC = "12574478"

ep_params = {
    "device": "HMA-AL00",
    "isBeta": "false",
    "grayHair": "false",
    "from": "nt_history",
    "brand": "HUAWEI",
    "info": "wifi",
    "index": "4",
    "rainbow": "",
    "schemaType": "auction",
    "elderHome": "false",
    "isEnterSrpSearch": "true",
    "newSearch": "false",
    "network": "wifi",
    "subtype": "",
    "hasPreposeFilter": "false",
    "prepositionVersion": "v2",
    "client_os": "Android",
    "gpsEnabled": "false",
    "searchDoorFrom": "srp",
    "debug_rerankNewOpenCard": "false",
    "homePageVersion": "v7",
    "searchElderHomeOpen": "false",
    "search_action": "initiative",
    "sugg": "_4_1",
    "sversion": "13.6",
    "style": "list",
    "ttid": "600000@taobao_pc_10.7.0",
    "needTabs": "true",
    "areaCode": "CN",
    "vm": "nw",
    "countryNum": "156",
    "m": "pc",
    "page": 2,
    "n": 48,
    "q": "%E5%81%A5%E8%BA%AB%E5%99%A8%E6%9D%90",
    "qSource": "manual",
    "pageSource": "a21bo.jianhua/a.search_history.d1",
    "channelSrp": "",
    "tab": "all",
    "pageSize": "50",
    "totalPage": "100",
    "totalResults": "124014",
    "sourceS": 1,
    "sort": "_coefp",
    "bcoffset": -15,
    "ntoffset": 0,
    "filterTag": "",
    "service": "",
    "prop": "",
    "loc": "",
    "start_price": None,
    "end_price": None,
    "startPrice": None,
    "endPrice": None,
    "categoryp": "",
    "ha3Kvpairs": None,
    "couponFilter": 0,
    "myCNA": "cRksIuJR9nICAT3ym4dXCcjf",
    "screenResolution": "1463x915",
    "viewResolution": "667x4771",
    "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    "couponUnikey": "",
    "subTabId": "",
    "np": "",
    "clientType": "h5",
    "isNewDomainAb": "false",
    "forceOldDomain": "false"
}

data = {
    "appId": "34385",
    "params": json.dumps(ep_params, separators=(',', ':'))
}
ep_data = json.dumps(data, separators=(',', ':'))
# 加密传入的值
string = token + "&" + str(eT) + "&" + eC + "&" + ep_data
sign = hashlib.md5(string.encode('utf-8')).hexdigest()
print(sign)
# 模拟浏览器
headers = {
    # cookie 检查是否有登陆账号
    'cookie' : "",
    # referer 防盗链, 请求网址哪里跳转来的
    'referer' : "https://s.taobao.com/search?_input_charset=utf-8&clientPreloadId=preload_1774431054945&commend=all&ie=utf8&initiative_id=tbindexz_20170306&page=2&preLoadOrigin=https%3A%2F%2Fwww.taobao.com&q=%E9%94%AE%E7%9B%98&search_type=item&source=suggest&sourceId=tb.index&spm=a21bo.jianhua%2Fa.search_history.d1&ssid=s5-e&suggest_query=&tab=all&wq=",
    # user-agent 浏览器设备基本身份信息
    'user-agent' : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
}

# 请求网址
url = 'https://h5api.m.taobao.com/h5/mtop.relationrecommend.wirelessrecommend.recommend/2.0/'

# 查询参数
params = {
    'jsv':'2.7.4',
    'appKey':'12574478',
    't':eT,
    'sign':sign,
    'api':'mtop.relationrecommend.wirelessrecommend.recommend',
    'v':'2.0',
    'timeout':'10000',
    'type':'jsonp',
    'dataType':'jsonp',
    'callback':'mtopjsonp6',
    'data':ep_data,
    'bx-ua':'fast-load',
}

# 发送请求
response = requests.get(url=url, params=params, headers=headers)

"""获取数据"""
text = response.text
text_json = re.findall('mtopjsonp6\((.*)', text)[0][:-1]
json_data = json.loads(text_json)

# 安全获取数据，不存在就返回空列表，不会报错
if 'data' in json_data and 'itemsArray' in json_data['data']:
    itemsArray = json_data['data']['itemsArray']
    print('获取到商品数量：', len(itemsArray))
else:
    print('接口没有返回商品数据！！！')
    itemsArray = []  # 空列表，避免报错

for index in itemsArray:
    try:
        # 提取地区信息
        area_info = index['procity'].split(' ')
        if len(area_info) == 2:
            area = area_info[0]
            city = area_info[1]
        else:
            area = area_info[0]
            city = '未知'
        dit = {
            '标题' : index['title'].replace('<span class=H>', '').replace('</span>', ''),
            '店铺' : index['nick'],
            '价格' : index['price'],
            '省份' : area,
            '城市' : city,
            '销量' : index['realSales'],
            '商品ID' : index['item_id'],
            '商品链接' : index['auctionURL'],
        }
        csv_writer.writerow(dit)
        print(dit)
    except:
        pass
