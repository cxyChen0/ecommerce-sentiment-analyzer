# 电商智能选品分析系统

一个基于AI的电商智能选品分析工具，支持真实数据爬取、AI情感分析和竞品对比，帮助电商从业者做出更明智的选品决策。

## 项目结构

```
ecommerce-sentiment-analyzer/
├── app.py                    # 🚀 主应用（Streamlit）
├── analysis.py               # 🤖 AI分析模块
├── crawler.py                # 🕷️ 数据爬虫
├── requirements.txt          # 📦 Python依赖
├── setup.sh                  # ⚙️ 部署脚本
├── DEPLOYMENT.md             # 📖 部署指南
├── SHARING_GUIDE.md          # 📤 分享指南
├── README.md                 # 📝 项目说明
├── .gitignore               # 🚫 Git忽略规则
├── .env.example             # 🔒 环境变量模板
└── .streamlit/              # ⚙️ Streamlit配置
    └── config.toml          # 📋 服务器配置
```

## 如何使用项目

### 本地开发环境运行

1. **克隆项目**
   ```bash
   # 从GitHub克隆
   git clone https://github.com/cxyChen0/ecommerce-sentiment-analyzer.git
   
   # 或从Gitee克隆（如果已创建）
   git clone https://gitee.com/cxyChen0/ecommerce-sentiment-analyzer.git
   
   cd ecommerce-sentiment-analyzer
   ```

2. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

3. **配置环境变量**
   ```bash
   # 复制模板文件为.env
   cp .env.example .env
   
   # 编辑.env文件，添加您的API Key
   # 例如：ALIYUN_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
   ```

4. **运行Streamlit应用**
   ```bash
   streamlit run app.py
   ```

5. **访问应用**
   - 在浏览器中打开 `http://localhost:8501`
   - 输入商品链接或关键词进行分析
   - 查看AI生成的分析报告

### 云端部署

项目支持多种云端部署方案，详细请查看 `DEPLOYMENT.md` 文件。

推荐使用 **Streamlit Cloud** 进行部署，简单快捷：
1. 访问：https://share.streamlit.io/
2. 连接您的GitHub仓库
3. 设置应用入口文件为 `app.py`
4. 配置环境变量（如需使用AI功能）

## 主要功能

- ✅ 电商平台评论数据爬取（支持天猫/淘宝）
- ✅ 单品深度体验分析
- ✅ 市场趋势与竞品调研
- ✅ 竞品差异化对比分析
- ✅ AI情感分析（基于阿里云百炼）
- ✅ 多线程数据采集
- ✅ 响应式界面设计
- ✅ 云端部署就绪

## 技术栈

- **前端框架**：Streamlit
- **数据处理**：Pandas
- **AI分析**：OpenAI兼容API（阿里云百炼）
- **爬虫**：Selenium + webdriver-manager
- **HTTP请求**：Requests
- **环境管理**：python-dotenv

## 配置说明

1. **环境变量配置**
   - 复制 `.env.example` 为 `.env` 文件
   - 编辑 `.env` 文件，添加所需的API密钥
   - 主要配置项：
     ```
     # 阿里云百炼 API Key（必填，用于AI分析）
     ALIYUN_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
     ```

2. **爬虫配置**
   - 爬虫默认配置已在 `crawler.py` 中定义
   - 主要配置项：
     - `MAX_COMMENTS`: 最大评论数（默认200）
     - `SCROLL_PAUSE_MIN/MAX`: 滚动等待时间

## 注意事项

1. **真实爬虫使用**
   - 爬虫功能需要Chrome浏览器
   - 频繁爬取可能导致IP被封禁，请合理使用
   - 建议在本地开发环境测试爬虫功能

2. **API密钥安全**
   - 不要将包含真实API密钥的 `.env` 文件提交到公共仓库
   - `.env` 文件已被加入 `.gitignore`，不会被自动提交

3. **依赖版本**
   - 如遇到依赖冲突，建议使用虚拟环境
   - 可以使用 `pip install -r requirements.txt --no-cache-dir` 强制更新依赖

## 如何共享项目

详细的项目共享指南请查看 `SHARING_GUIDE.md` 文件，包括：
- GitHub/Gitee直接下载
- Git克隆方式
- 项目结构说明
- 快速启动指南

## 更新日志

- v1.0.0: 初始版本，支持基本的爬虫、分析功能
- v1.1.0: 新增AI情感分析模块
- v1.2.0: 优化UI界面，添加更多分析功能
- v1.3.0: 支持多线程数据采集和竞品对比
- v1.4.0: 优化依赖管理，完善部署文档

## 联系方式

如有问题或建议，欢迎通过GitHub Issues联系项目维护者。

---

**项目地址**：
- GitHub: https://github.com/cxyChen0/ecommerce-sentiment-analyzer
- Gitee: https://gitee.com/cxyChen0/ecommerce-sentiment-analyzer（待创建）
