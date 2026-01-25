# 🚀 电商智能选品分析系统 - 分享指南

## 📦 完整项目下载

### 方法一：直接下载ZIP包

#### GitHub
1. 访问：https://github.com/cxyChen0/ecommerce-sentiment-analyzer
2. 点击绿色的 "Code" 按钮
3. 选择 "Download ZIP"
4. 解压后即可获得完整代码

#### Gitee
1. 访问：https://gitee.com/cxyChen0/ecommerce-sentiment-analyzer（如果已配置）
2. 点击右上角的 "克隆/下载" 按钮
3. 选择 "下载ZIP"
4. 解压后即可获得完整代码

### 方法二：Git克隆（需要Git）

#### GitHub
```bash
git clone https://github.com/cxyChen0/ecommerce-sentiment-analyzer.git
cd ecommerce-sentiment-analyzer
```

#### Gitee
```bash
git clone https://gitee.com/cxyChen0/ecommerce-sentiment-analyzer.git
cd ecommerce-sentiment-analyzer
```

## 📁 项目结构说明

```
ecommerce-sentiment-analyzer/
├── app.py                    # 🚀 主应用（Streamlit）
├── main.py                   # 🔄 备用应用
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

## ⚡ 快速启动

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

#### 方法一：使用.env.example模板
```bash
# 复制模板文件为.env
cp .env.example .env

# 编辑.env文件，添加您的API Key
# 使用文本编辑器打开.env文件，例如：
# nano .env 或 notepad .env
# 然后添加：
# ALIYUN_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
```

#### 方法二：直接设置环境变量
```bash
# Windows (cmd)
set ALIYUN_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx

# Windows (PowerShell)
$env:ALIYUN_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxx"

# Linux/Mac
export ALIYUN_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
```

### 3. 运行应用
```bash
streamlit run app.py
```

## 🌐 云端部署

项目已配置好云端部署，可以直接部署到：
- **Streamlit Cloud**：https://share.streamlit.io/
- **Heroku**：使用setup.sh脚本
- **Railway**：一键部署

## 📊 功能特性

- ✅ 电商数据分析
- ✅ AI情感分析
- ✅ 数据可视化
- ✅ 爬虫数据采集
- ✅ 响应式界面设计
- ✅ 云端部署就绪

## 🔧 技术栈

- **前端**：Streamlit
- **数据处理**：Pandas
- **可视化**：Plotly
- **AI分析**：OpenAI API
- **爬虫**：Selenium + webdriver-manager

## 📞 联系方式

如有问题，请通过GitHub Issues联系。

---
*创建时间：2026-01-01*
*版本：v1.0*
*作者：cxyChen0*