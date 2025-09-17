import json
import feedparser
import re
import time
import requests
import os
from datetime import datetime
import concurrent.futures
from urllib.parse import urlparse

class RSSCrawler:
    def __init__(self, config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
        self.all_links_file = self.config.get('output_file', 'all_links.txt')
        self.rss_feeds = self.config.get('rss_feeds', [])
        self.interval = self.config.get('interval', 3600)
        self.concurrent_requests = self.config.get('concurrent_requests', 5)
        self.timeout = self.config.get('timeout', 10)
        
        # 定义支持的所有网盘域名模式
        self.cloud_domains = {
            'baidu': ['pan.baidu.com', 'yun.baidu.com', '百度网盘'],
            'aliyun': ['aliyundrive.com', '阿里云盘'],
            'quark': ['quark.cn', '夸克网盘'],
            'tianyi': ['cloud.189.cn', '天翼云盘'],
            'uc': ['drive.uc.cn', 'UC网盘'],
            'mobile': ['cloud.10086.cn', '移动云盘'],
            '115': ['115.com', '115cdn.com', '115网盘'],
            'pikpak': ['pikpak.com', 'PikPak'],
            'xunlei': ['pan.xunlei.com', '迅雷网盘'],
            '123': ['123pan.com', '123网盘'],
            'magnet': ['magnet:?xt='],
            'ed2k': ['ed2k://']
        }
        
        # 定义所有网盘链接正则表达式
        self.link_patterns = [
            # 百度网盘
            r'(https?://pan\.baidu\.com/s/[\w\-]+)',
            r'(https?://yun\.baidu\.com/s/[\w\-]+)',
            # 阿里云盘
            r'(https?://www\.aliyundrive\.com/s/[\w\-]+)',
            r'(https?://aliyundrive\.com/s/[\w\-]+)',
            # 夸克网盘
            r'(https?://quark\.cn/s/[\w\-]+)',
            # 天翼云盘
            r'(https?://cloud\.189\.cn/web/share\?code=[\w\-]+)',
            r'(https?://cloud\.189\.cn/t/[\w\-]+)',
            # UC网盘
            r'(https?://drive\.uc\.cn/s/[\w\-]+)',
            # 移动云盘
            r'(https?://cloud\.10086\.cn/t/[\w\-]+)',
            # 115网盘 - 支持新老格式和带提取码的链接
            r'(https?://115\.com/lb/\?s=[\w\-]+)',
            r'(https?://115cdn\.com/s/[\w\-]+(\?password=[\w\-]+)?#?)',
            # PikPak
            r'(https?://api\.pikpak\.com/drive/v1/files/[\w\-]+/share)',
            r'(https?://pikpak\.com/s/[\w\-]+)',
            # 迅雷网盘
            r'(https?://pan\.xunlei\.com/s/[\w\-]+)',
            # 123网盘
            r'(https?://www\.123pan\.com/s/[\w\-]+)',
            # 磁力链接
            r'(magnet:\?xt=urn:btih:[a-fA-F0-9]{40}(&[\w\-\=]+)*)',
            # 电驴链接
            r'(ed2k://\|file\|[^\|]+\|[0-9]+\|[A-F0-9]{32}\|/)'
        ]
        
        # 已爬取的链接集合，避免重复
        self.crawled_links = set()
        # 加载已存在的链接
        self._load_existing_links()
        # 记录最近爬取失败的链接
        self.failed_feeds = set()
        # 创建会话对象以提高性能
        self.session = requests.Session()
    
    def _load_existing_links(self):
        """加载已爬取的链接，避免重复"""
        if os.path.exists(self.all_links_file):
            try:
                with open(self.all_links_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            self.crawled_links.add(line.strip())
                print(f"已加载 {len(self.crawled_links)} 个已存在的链接")
            except Exception as e:
                print(f"加载已存在链接时出错: {e}")
    
    def _extract_s_links(self, content):
        """专门提取带有/s/路径的网盘链接"""
        s_links = set()
        
        # 定义带有/s/路径的链接模式
        s_link_patterns = [
            # 百度网盘
            r'(https?://pan\.baidu\.com/s/[\w\-]+)',
            r'(https?://yun\.baidu\.com/s/[\w\-]+)',
            # 阿里云盘
            r'(https?://www\.aliyundrive\.com/s/[\w\-]+)',
            r'(https?://aliyundrive\.com/s/[\w\-]+)',
            # 夸克网盘
            r'(https?://quark\.cn/s/[\w\-]+)',
            # UC网盘
            r'(https?://drive\.uc\.cn/s/[\w\-]+)',
            # 115网盘 - 支持带提取码的链接
            r'(https?://115cdn\.com/s/[\w\-]+(\?password=[\w\-]+)?#?)',
            # PikPak
            r'(https?://pikpak\.com/s/[\w\-]+)',
            # 迅雷网盘
            r'(https?://pan\.xunlei\.com/s/[\w\-]+)',
            # 123网盘
            r'(https?://www\.123pan\.com/s/[\w\-]+)',
            # 通用/s/链接模式，捕获其他可能的网盘链接
            r'(https?://[\w\-]+\.[\w\-]+/s/[\w\-]+)',
        ]
        
        # 使用正则表达式提取带有/s/的链接
        for pattern in s_link_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            # 处理元组结果（如果有分组）
            for match in matches:
                if isinstance(match, tuple):
                    # 取第一个非空的分组
                    for group in match:
                        if group:
                            s_links.add(group)
                            break
                else:
                    s_links.add(match)
        
        return s_links
    
    def _extract_links(self, content):
        """从内容中提取所有支持的网盘链接，优先提取带有/s/的链接"""
        # 首先提取带有/s/的链接
        links = self._extract_s_links(content)
        
        # 然后使用原始的正则表达式提取其他链接作为补充
        for pattern in self.link_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            # 处理元组结果（如果有分组）
            for match in matches:
                if isinstance(match, tuple):
                    # 取第一个非空的分组
                    for group in match:
                        if group:
                            links.add(group)
                            break
                else:
                    links.add(match)
        
        # 使用域名匹配提取链接（除了已经通过_s_links提取的/s/链接）
        for 网盘_type, domains in self.cloud_domains.items():
            for domain in domains:
                # 特殊处理磁力链接和电驴链接
                if domain.startswith('magnet:?xt=') or domain.startswith('ed2k://'):
                    continue  # 这些已经通过正则表达式处理过了
                
                # 跳过已经在_s_links中处理过的域名
                if '/s/' in domain:
                    continue
                
                # 处理中文域名或名称
                if any(char > '\u007f' for char in domain):  # 检查是否包含非ASCII字符（中文）
                    if domain in content:
                        # 尝试提取包含中文域名的URL
                        url_pattern = r'(https?://[\w\-]+\.?'+ re.escape(re.sub(r'[^\u4e00-\u9fa5]', '', domain)) + r'[\w\-/.?&=%]+)'
                        matches = re.findall(url_pattern, content, re.IGNORECASE)
                        links.update(matches)
                else:
                    # 处理英文域名
                    url_pattern = r'(https?://[\w\-]+\.?' + re.escape(domain) + r'[\w\-/.?&=%]+)'
                    matches = re.findall(url_pattern, content, re.IGNORECASE)
                    links.update(matches)
        
        # 额外处理磁力链接和电驴链接的变体
        magnet_pattern = r'(magnet:\?[^\s"\']+)'  # 捕获任何以magnet:?开头的链接
        ed2k_pattern = r'(ed2k://[^\s"\']+)'  # 捕获任何以ed2k://开头的链接
        
        magnet_matches = re.findall(magnet_pattern, content, re.IGNORECASE)
        ed2k_matches = re.findall(ed2k_pattern, content, re.IGNORECASE)
        
        links.update(magnet_matches)
        links.update(ed2k_matches)
        
        return links
    
    def _get_timestamp_filename(self):
        """生成按时间命名的文件名，格式为月日+24小时制时间，例如09030110"""
        now = datetime.now()
        return now.strftime("%m%d%H%M.txt")
    
    def _save_links(self, new_links):
        """保存新发现的链接到按时间命名的文件和总链接文件"""
        if not new_links:
            print("本次爬取未发现新的链接")
            return
        
        # 生成时间戳文件名
        timestamp_filename = self._get_timestamp_filename()
        
        # 保存到时间戳文件
        with open(timestamp_filename, 'w', encoding='utf-8') as f:
            # 添加文件头部信息
            f.write(f"===== 爬取时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} =====\n")
            f.write(f"===== 发现链接数：{len(new_links)} =====\n\n")
            
            for link in new_links:
                f.write(f"{link}\n")
        
        # 保存到总链接文件
        with open(self.all_links_file, 'a', encoding='utf-8') as f:
            for link in new_links:
                f.write(f"{link}\n")
                self.crawled_links.add(link)
        
        print(f"已保存 {len(new_links)} 个新的网盘链接")
        print(f"时间戳文件：{timestamp_filename}")
        print(f"总链接文件：{self.all_links_file}")
    
    def _crawl_single_feed(self, feed_url, retry_count=3):
        """爬取单个RSS订阅源，带重试机制"""
        new_links = set()
        attempt = 0
        
        while attempt < retry_count:
            try:
                print(f"正在爬取RSS订阅源: {feed_url} (尝试 {attempt + 1}/{retry_count})")
                
                # 使用feedparser的默认HTTP处理，移除handlers参数和timeout参数以避免版本兼容性问题
                # 添加随机延迟避免请求过快
                import random
                time.sleep(random.uniform(1, 3))  # 添加1-3秒的随机延迟
                
                feed = feedparser.parse(feed_url)
                
                if feed.bozo:
                    error_msg = str(feed.bozo_exception)
                    print(f"解析RSS失败: {error_msg}")
                    # 特别处理连接关闭错误
                    if "Remote end closed connection without response" in error_msg:
                        print("检测到连接被远程服务器关闭，将增加重试间隔...")
                        time.sleep(5)  # 连接关闭错误时增加等待时间
                    attempt += 1
                    if attempt < retry_count:
                        print(f"等待 {2 * (attempt)} 秒后重试...")
                        time.sleep(2 * attempt)  # 指数退避策略
                    continue
                
                # 遍历每个条目
                for entry in feed.entries:
                    # 组合标题、摘要和内容用于链接提取
                    content = ''
                    if 'title' in entry:
                        content += entry.title + '\n'
                    if 'summary' in entry:
                        content += entry.summary + '\n'
                    if 'content' in entry:
                        for c in entry.content:
                            content += c.value + '\n'
                    
                    # 提取链接
                    links = self._extract_links(content)
                    
                    # 检查链接是否已存在
                    for link in links:
                        if link not in self.crawled_links:
                            new_links.add(link)
                
                # 成功爬取，退出循环
                if feed_url in self.failed_feeds:
                    self.failed_feeds.remove(feed_url)
                print(f"成功爬取 {feed_url}，发现 {len(new_links)} 个链接")
                return new_links
            except Exception as e:
                error_msg = str(e)
                print(f"爬取RSS订阅源时出错: {error_msg}")
                # 特别处理连接关闭错误
                if "Remote end closed connection without response" in error_msg:
                    print("检测到连接被远程服务器关闭，将增加重试间隔...")
                    time.sleep(5)  # 连接关闭错误时增加等待时间
                attempt += 1
                if attempt < retry_count:
                    print(f"等待 {2 * (attempt)} 秒后重试...")
                    time.sleep(2 * attempt)  # 指数退避策略
                else:
                    print(f"RSS订阅源 {feed_url} 多次尝试后仍然失败，将其添加到失败列表")
                    self.failed_feeds.add(feed_url)
        
        return new_links
    
    def _requests_handler(self, url, timeout=None, **kwargs):
        """使用requests库处理HTTP请求"""
        if timeout is None:
            timeout = self.timeout
        
        try:
            response = self.session.get(url, timeout=timeout, **kwargs)
            response.raise_for_status()
            return response.content
        except Exception as e:
            raise Exception(f"请求失败: {e}")
    
    def crawl_rss_feed(self, feed_url):
        """爬取单个RSS订阅源的公共接口"""
        return self._crawl_single_feed(feed_url)
    
    def run(self, continuous=False):
        """运行爬虫，支持并发爬取"""
        while True:
            print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始爬取...")
            print(f"总共有 {len(self.rss_feeds)} 个RSS订阅源需要爬取")
            all_new_links = set()
            
            # 降低并发请求数量，避免过快请求导致连接被关闭
            # 获取当前设置的并发数，如果过高则降低
            concurrent_workers = min(self.concurrent_requests, 3)  # 限制最大并发数为3
            print(f"使用 {concurrent_workers} 个并发线程进行爬取")
            
            # 使用线程池并发爬取
            with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_workers) as executor:
                # 提交所有爬取任务
                future_to_feed = {
                    executor.submit(self.crawl_rss_feed, feed_url): feed_url
                    for feed_url in self.rss_feeds
                }
                
                # 处理完成的任务
                for future in concurrent.futures.as_completed(future_to_feed):
                    feed_url = future_to_feed[future]
                    try:
                        new_links = future.result()
                        all_new_links.update(new_links)
                        print(f"完成爬取 {feed_url}，发现 {len(new_links)} 个新链接")
                    except Exception as e:
                        print(f"爬取 {feed_url} 时发生异常: {e}")
                        self.failed_feeds.add(feed_url)
            
            # 保存新发现的链接
            self._save_links(all_new_links)
            
            # 打印失败统计
            if self.failed_feeds:
                print(f"本次爬取有 {len(self.failed_feeds)} 个订阅源失败")
                # 将失败的订阅源追加到固定的失败记录文件，而不是每次生成新文件
                failed_file = "failed_feeds.log"
                with open(failed_file, 'a', encoding='utf-8') as f:
                    # 添加时间标记和分隔符
                    f.write(f"\n========== 爬取时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ==========\n")
                    f.write(f"本次失败订阅源数量：{len(self.failed_feeds)}\n")
                    for feed in self.failed_feeds:
                        f.write(f"{feed}\n")
                print(f"失败订阅源已追加到：{failed_file}")
            
            if not continuous:
                break
            
            print(f"等待 {self.interval} 秒后再次爬取...")
            time.sleep(self.interval)

if __name__ == "__main__":
    crawler = RSSCrawler('config.json')
    # 单次运行爬虫
    crawler.run(continuous=False)
    # 如果要持续运行爬虫，可以使用：
    # crawler.run(continuous=True)