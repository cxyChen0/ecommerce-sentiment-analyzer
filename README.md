# 电商客户体验分析系统

一个基于AI的电商平台客户购买体验分析工具，支持真实数据爬取和模拟数据演示。

## 项目结构

```
PyCharm2023/
├── main.py              # 主程序入口（Streamlit应用）
├── analysis.py          # 数据分析模块
├── app.py               # 应用配置
├── auto_typer.py        # 自动打字功能
├── crawler.py           # 爬虫模块
├── requirements.txt     # 项目依赖
├── .env                 # 环境变量配置
├── dist/                # 打包后的可执行文件
│   └── PTA神速打字机.exe
└── build/               # 打包构建目录
```

## 如何共享项目

### 方式一：通过代码仓库共享（适合开发者）

1. **初始化Git仓库**
   ```bash
   git init
   git add .
   git commit -m "初始化项目"
   ```

2. **创建.gitignore文件**
   ```
   # Python
   __pycache__/
   *.pyc
   *.pyo
   *.pyd

   # 环境变量
   .env
   
   # 打包文件
   build/
   dist/
   *.spec
   
   # IDE
   .idea/
   *.iml
   
   # 数据文件
   *.csv
   ```

3. **推送到远程仓库**
   ```bash
   git remote add origin <你的远程仓库地址>
   git push -u origin main
   ```

4. **共享给他人**
   - 分享远程仓库地址给其他人
   - 他人克隆仓库：`git clone <仓库地址>`
   - 安装依赖：`pip install -r requirements.txt`
   - 运行项目：`streamlit run main.py`

### 方式二：通过可执行文件共享（适合普通用户）

1. **使用已有的打包文件**
   - 项目已通过PyInstaller打包，可执行文件位于 `dist/` 目录下
   - 直接将 `dist/PTA神速打字机.exe` 文件发送给他人
   - 他人无需安装Python环境，直接运行.exe文件即可

2. **重新打包项目（可选）**
   ```bash
   pyinstaller --onefile --windowed main.py
   # 或使用已有spec文件
   pyinstaller PTA神速打字机.spec
   ```

### 方式三：通过Docker容器共享（适合需要完整环境的用户）

1. **创建Dockerfile**
   ```dockerfile
   FROM python:3.11-slim
   
   WORKDIR /app
   
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   
   COPY . .
   
   EXPOSE 8501
   
   CMD ["streamlit", "run", "main.py"]
   ```

2. **构建Docker镜像**
   ```bash
   docker build -t ecommerce-analysis .
   ```

3. **运行Docker容器**
   ```bash
   docker run -p 8501:8501 ecommerce-analysis
   ```

4. **共享Docker镜像**
   ```bash
   # 保存镜像到文件
   docker save -o ecommerce-analysis.tar ecommerce-analysis
   
   # 他人加载镜像
   docker load -i ecommerce-analysis.tar
   ```

## 如何使用项目

### 开发环境运行

1. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

2. **运行Streamlit应用**
   ```bash
   streamlit run main.py
   ```

3. **访问应用**
   - 在浏览器中打开 `http://localhost:8501`
   - 输入商品链接，选择是否启用真实爬虫
   - 点击"开始分析"按钮查看结果

### 可执行文件运行

1. **直接运行**
   - 双击 `dist/PTA神速打字机.exe` 文件
   - 应用将自动启动

### 配置说明

1. **环境变量配置**
   - 编辑 `.env` 文件，添加所需的API密钥
   - 例如：`ALIYUN_API_KEY=your_api_key`

2. **爬虫配置**
   - 如需使用真实爬虫功能，需配置Cookie
   - 请参考爬虫模块的代码注释进行配置

## 主要功能

- ✅ 电商平台评论数据爬取
- ✅ AI情感分析（支持真实API和模拟模式）
- ✅ 销量趋势可视化
- ✅ 情感分布饼图
- ✅ 详细评论数据展示
- ✅ 支持真实数据和模拟数据切换

## 技术栈

- **前端框架**：Streamlit
- **数据处理**：Pandas
- **可视化**：Plotly
- **AI分析**：DeepSeek API（可切换模拟模式）
- **爬虫**：Selenium、Requests
- **打包工具**：PyInstaller

## 注意事项

1. **真实爬虫使用**
   - 真实爬虫需要有效的Cookie，否则可能被反爬拦截
   - 爬虫速度较慢，建议在演示时使用模拟数据
   - 频繁爬取可能导致IP被封禁，请合理使用

2. **API密钥安全**
   - 不要将包含真实API密钥的代码或.env文件提交到公共仓库
   - 建议使用环境变量或配置文件管理敏感信息

3. **依赖版本**
   - 如遇到依赖冲突，建议使用虚拟环境
   - 可以使用 `pip install -r requirements.txt --no-cache-dir` 强制更新依赖

## 更新日志

- v1.0.0: 初始版本，支持基本的爬虫、分析和可视化功能
- v1.1.0: 新增AI情感分析，支持真实API和模拟模式切换
- v1.2.0: 优化了UI界面，添加了更多可视化图表

## 联系方式

如有问题或建议，欢迎联系项目维护者。
