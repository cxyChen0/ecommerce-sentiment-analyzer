import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class ECommerceCrawler:
    def __init__(self):
        # 1. 基础配置：模拟真实浏览器的身份 (User-Agent)
        # 建议：在浏览器按F12 -> Network -> 刷新页面 -> 点击第一个请求 -> 复制 User-Agent
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
            # 2. 关键点：Cookie
            # 真实抓取淘宝/京东必须填入登录后的Cookie，否则会被重定向到登录页
            # 获取方法：F12 -> Network -> Doc -> Headers -> Request Headers -> Cookie
            'Cookie': 't=23d0ff65a3c0a9f193deec98068caa42; thw=cn; cna=idSBIT60gE0CAdNbuK0yIMez; isg=BAYG_wC1kuuqo0aP_KS4KQgGV_yIZ0oh8AkNhvAuXCmr86UNWPdSM-zCzy8_3UI5; miid=6194848056817364960; cookie2=19d31ce814fe97efc5b8aa26f24936d6; _tb_token_=6e338feb7e79; tkSid=1763885460610_554137597_0.0; ctoken=uR2DSndvRSnSBTYHZh6w5nt5; lego2_cna=XD00HD2TMC4ER848MRUR8MDM; __wpkreporterwid_=3e1ed0a3-342b-4559-8408-7146cb2f2d92; _samesite_flag_=true; 3PcFlag=1763885461954; xlly_s=1; sgcookie=E1009w9%2Box%2F2MMuZDvVlfVwrKj932xSaBwihrrcccTOuVoiYDFzznvSS7B2tnOT%2FLTTNe81fBQdNcrbUtQ8SL2L6pV6a3bIcBcYj3AXXkyNIiw0%3D; wk_cookie2=1714d76970c3f3ea6b39d7dafe2a678f; wk_unb=UNJW7JE8H4ehew%3D%3D; unb=3274212352; uc1=existShop=false&cookie21=V32FPkk%2FgihF%2FS5nr3O5&cookie14=UoYY4HE6HWKNxA%3D%3D&cookie15=UIHiLt3xD8xYTw%3D%3D&pas=0&cookie16=UtASsssmPlP%2Ff1IHDsDaPRu%2BPw%3D%3D; uc3=vt3=F8dD2klrAyEOM7mtw24%3D&nk2=1pW4RXFIlSOzSg%3D%3D&lg2=VFC%2FuZ9ayeYq2g%3D%3D&id2=UNJW7JE8H4ehew%3D%3D; csg=60e6f6f1; lgc=%5Cu7B2C%5Cu4E00%5Cu9648%5Cu970F%5Cu53F7; cancelledSubSites=empty; cookie17=UNJW7JE8H4ehew%3D%3D; dnk=cxy_chen; skt=7b41402b6ac83b1d; existShop=MTc2Mzg4NTQ5Nw%3D%3D; uc4=id4=0%40UgXR3FLHNrJ3XRPg6k2N2m%2B5K22C&nk4=0%401CStfcTVIFai4oDkck7degtgYp0a; tracknick=%5Cu7B2C%5Cu4E00%5Cu9648%5Cu970F%5Cu53F7; _cc_=UIHiLt3xSw%3D%3D; _l_g_=Ug%3D%3D; sg=%E5%8F%B726; _nk_=%5Cu7B2C%5Cu4E00%5Cu9648%5Cu970F%5Cu53F7; cookie1=UoTV6y3McdkUHtjEJ%2B5qocln%2FvqKuRAFLE%2Bu6usnvaU%3D; mtop_partitioned_detect=1; _m_h5_tk=d79f725e4f919b7603daa6d8e04b919a_1763895580358; _m_h5_tk_enc=5aabcae367373f4c23e31a211f53c696; tfstk=f9x6l32z55V1B2QTzKHUPMHPUgjjLCirc-6vEKEaHGIOcm1BOZEqSG7fcBCeb1JNX-OXTQ_tIsu0IeAyel-ZSirfjijxabor4p9GmiKO2emAspphH9M5L3JMIi23LS3yJdmfGuxz5idAv6BPUiBOkZHQJt5LXtEOHWHCnEZbrXitDKuajlzozuwvpKEYDHnc5_9TuoEvAO_6DdCB7F-CCN1RlMjjzhdeHh-G-cE1mp8WGEd-TP59PTOCzFG7fQOGHK6v10259h9XANYU6PB5f1_JXBeuxL_vRHswXj4kLp1OPM8E-f7VfCTlZN3ntI9C_IK1J5sPFu558KUbdaqfd_kIdr40GgLSghwZ4j_OK9kSdvaPWNBhd_kIdr4cW9XeVvMQzNC..'
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)

    def fetch_page(self, url):
        """
        发送网络请求，获取网页源码
        """
        try:
            # 3. 随机延时：防止请求太快被封IP (模拟人类操作: 2-5秒)
            sleep_time = random.uniform(2, 5)
            logging.info(f"等待 {sleep_time:.2f} 秒后开始抓取: {url}")
            time.sleep(sleep_time)

            response = self.session.get(url, timeout=10)

            # 检查状态码
            if response.status_code == 200:
                logging.info("页面请求成功！")
                return response.text
            else:
                logging.error(f"请求失败，状态码: {response.status_code}")
                return None
        except Exception as e:
            logging.error(f"发生网络错误: {e}")
            return None

    def parse_tmall_comments(self, html):
        """
        解析天猫/淘宝的评论数据 (示例解析逻辑)
        注意：电商网站的 CSS 类名会经常变动，如果抓不到数据，需要按 F12 检查最新的类名
        """
        soup = BeautifulSoup(html, 'html.parser')
        comments_data = []

        # 4. 定位评论元素 (这里使用通用的结构查找，实际需要根据网页最新结构调整)
        # 提示：很多现代电商评论是动态加载的 (AJAX)，requests 可能抓不到，
        # 如果抓不到，需要分析 Network 中的 JSON 接口，或者使用 Selenium。

        # 假设我们抓取的是一个静态页面的结构示例：
        comment_items = soup.find_all('div', class_='rate-grid-item')  # 这是一个典型的评论容器类名示例

        if not comment_items:
            logging.warning(
                "未找到评论元素，可能是因为：1. Cookie失效 2. 页面是动态加载的(需要Selenium) 3.由于反爬被拦截")
            return []

        for item in comment_items:
            try:
                # 提取评论内容
                content_tag = item.find('div', class_='tm-rate-content')
                content = content_tag.get_text(strip=True) if content_tag else "无内容"

                # 提取日期
                date_tag = item.find('span', class_='tm-rate-date')
                date = date_tag.get_text(strip=True) if date_tag else "未知日期"

                comments_data.append({
                    "content": content,
                    "date": date,
                    "source": "真实抓取"
                })
            except AttributeError:
                continue

        return comments_data

    def run(self, product_url):
        html = self.fetch_page(product_url)
        if html:
            # 解析数据
            data = self.parse_tmall_comments(html)

            if data:
                # 5. 保存数据
                df = pd.DataFrame(data)
                filename = f"real_data_{int(time.time())}.csv"
                df.to_csv(filename, index=False, encoding='utf-8-sig')
                logging.info(f"抓取完成！数据已保存为: {filename}")
                return df
            else:
                logging.warning("解析结果为空，未获取到有效数据。")
        return None


# =================使用说明=================
if __name__ == "__main__":
    # 替换为你想要抓取的商品链接
    target_url = "https://detail.tmall.com/item.htm?id=969963951158&mi_id=0000ALSxIO1xRJw-xqWqmvyMVOAh-I5EvFPze0-GKcJwOMY&pvid=b8c28b81-5a4b-4bd1-b6ff-3ada7926b549&scm=1007.57291.421744.0&skuId=5919899984777&spm=tbpc.item_error.201876.d20.3a007dd60tcFIG&utparam=%7B%22x_object_type%22%3A%22item%22%2C%22matchType%22%3A%22dm_interest%22%2C%22item_price%22%3A%2228%22%2C%22umpCalled%22%3Atrue%2C%22pc_scene%22%3A%2220001%22%2C%22userId%22%3A3274212352%2C%22ab_info%22%3A%2247291%23421744%23-1%23%22%2C%22tpp_buckets%22%3A%2247291%23421744%23module%22%2C%22isLogin%22%3Atrue%2C%22abid%22%3A3%2C%22pc_pvid%22%3A%22b8c28b81-5a4b-4bd1-b6ff-3ada7926b549%22%2C%22isWeekLogin%22%3Afalse%2C%22rn%22%3A19%2C%22ump_price%22%3A%2228%22%2C%22isXClose%22%3Afalse%2C%22x_object_id%22%3A969963951158%7D&xxc=home_recommend"

    crawler = ECommerceCrawler()

    # 注意：如果不填写真实的 Cookie，这行代码大概率会抓取失败
    crawler.run(target_url)