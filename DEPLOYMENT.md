# 电商智能选品分析系统 - 云端部署指南

本指南提供多种云端部署方案，帮助您将项目部署到云端服务器，实现24/7在线访问。

## 项目准备

### 1. 确保项目可正常运行
- 本地测试通过：`streamlit run app.py`
- 检查依赖：`requirements.txt` 文件已包含所有必要依赖
- 已添加容错处理：openai模块缺失不会导致应用崩溃

### 2. 配置文件检查
- `.gitignore` 文件已添加，排除敏感信息和不必要的文件
- `.env` 文件已配置，包含必要的环境变量（部署时需要重新配置）
- `.env.example` 文件已提供，作为环境变量模板
- `.streamlit/config.toml` 已配置，适合本地开发和部署
- `setup.sh` 脚本已更新，包含完整的部署步骤

### 3. Gitee代码仓库准备
如果您使用Gitee作为代码仓库，确保：
- 项目已推送到Gitee仓库
- 仓库地址可公开访问（部署平台需要拉取代码）
- 分支名称设置为常用名称（如main或master）

## 部署方案一：Streamlit Cloud（推荐）

Streamlit Cloud是专门为Streamlit应用设计的托管平台，部署简单快捷，支持GitHub和Gitee仓库。

### 部署步骤

1. **准备工作**
   - 注册Streamlit Cloud账号：https://share.streamlit.io/
   - 将项目推送到GitHub或Gitee仓库

2. **创建部署**
   - 登录Streamlit Cloud控制台
   - 点击"New app"按钮
   - 选择您的代码仓库类型（GitHub或Gitee）
   - 选择您的仓库
   - 选择主分支（main/master）
   - 设置应用入口文件：`app.py`
   - 配置环境变量（可选）：
     - 点击"Advanced settings"
     - 添加环境变量：`ALIYUN_API_KEY=your_api_key`

3. **部署完成**
   - Streamlit Cloud会自动安装依赖并部署应用
   - 部署完成后，您将获得一个公开的URL，如：`https://your-app.streamlit.app/`

### 注意事项
- Streamlit Cloud提供免费和付费计划
- 免费计划有资源限制，适合小型应用
- 支持自动部署：推送代码到GitHub后，应用会自动更新

## 部署方案二：Heroku

Heroku是一个支持多种编程语言的云平台，适合部署Python应用。

### 部署步骤

1. **准备工作**
   - 注册Heroku账号：https://www.heroku.com/
   - 安装Heroku CLI：https://devcenter.heroku.com/articles/heroku-cli
   - 将项目推送到GitHub或Gitee仓库

2. **创建Heroku应用**
   ```bash
   # 登录Heroku
   heroku login
   
   # 创建新应用
   heroku create your-app-name
   
   # 添加Heroku remote
   heroku git:remote -a your-app-name
   ```

3. **配置文件**
   - 使用项目中已有的 `Procfile` 文件（如果没有，创建一个）：
     ```
     web: sh setup.sh && streamlit run app.py
     ```
   - 项目中已包含 `setup.sh` 文件，确保它有执行权限：
     ```bash
     chmod +x setup.sh
     ```

4. **部署应用**
   
   **从GitHub部署**：
   ```bash
   # 推送代码到Heroku
   git push heroku main
   
   # 打开应用
   heroku open
   ```
   
   **从Gitee部署**：
   ```bash
   # 克隆Gitee仓库到本地
   git clone https://gitee.com/your-username/your-repo.git
   cd your-repo
   
   # 添加Heroku remote
   heroku git:remote -a your-app-name
   
   # 推送代码到Heroku
   git push heroku main
   
   # 打开应用
   heroku open
   ```

5. **配置环境变量**
   ```bash
   heroku config:set ALIYUN_API_KEY=your_api_key
   ```

### 注意事项
- Heroku提供免费计划，有资源限制
- 免费应用30分钟无活动会自动休眠
- 需要安装Chrome浏览器用于Selenium爬虫

## 部署方案三：Docker容器化部署

使用Docker容器化部署，便于跨平台运行和管理。

### 部署步骤

1. **准备工作**
   - 安装Docker：https://docs.docker.com/get-docker/
   - 注册Docker Hub账号（可选）：https://hub.docker.com/
   - 从GitHub或Gitee克隆项目：
     ```bash
     # 从GitHub克隆
     git clone https://github.com/your-username/your-repo.git
     
     # 或从Gitee克隆
     git clone https://gitee.com/your-username/your-repo.git
     
     cd your-repo
     ```

2. **使用项目中的Dockerfile**
   - 项目中已包含Dockerfile（如果没有，创建一个）：
     ```dockerfile
     # 使用Python 3.11基础镜像
     FROM python:3.11-slim
     
     # 设置工作目录
     WORKDIR /app
     
     # 安装系统依赖
     RUN apt-get update && apt-get install -y \
         wget \
         gnupg \
         unzip \
         curl \
         libnss3 \
         libgconf-2-4 \
         libxss1 \
         libappindicator1 \
         libindicator7 \
         xvfb \
         libasound2 \
         libpulse0 \
         libfontconfig1 \
         libdbus-1-3 \
         --no-install-recommends \
         && rm -rf /var/lib/apt/lists/*
     
     # 安装Chrome浏览器
     RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
         && sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list' \
         && apt-get update \
         && apt-get install -y google-chrome-stable --no-install-recommends \
         && rm -rf /var/lib/apt/lists/*
     
     # 复制项目文件
     COPY requirements.txt .
     COPY . .
     
     # 安装Python依赖
     RUN pip install --no-cache-dir -r requirements.txt
     
     # 设置环境变量
     ENV PYTHONUNBUFFERED=1
     
     # 暴露端口
     EXPOSE 8501
     
     # 启动应用
     CMD ["streamlit", "run", "app.py"]
     ```

3. **构建Docker镜像**
   ```bash
   docker build -t ecommerce-analysis .
   ```

4. **本地测试Docker镜像**
   ```bash
   docker run -p 8501:8501 -e ALIYUN_API_KEY=your_api_key ecommerce-analysis
   ```

5. **部署到云端**
   - **方案A：部署到云服务器**
     - 在AWS/阿里云/腾讯云等平台购买云服务器
     - 安装Docker
     - 从GitHub或Gitee克隆项目，构建镜像
     - 或从Docker Hub拉取镜像
     - 运行容器：`docker run -d -p 80:8501 -e ALIYUN_API_KEY=your_api_key ecommerce-analysis`
   
   - **方案B：部署到容器服务**
     - AWS ECS、阿里云ECS、腾讯云TKE等
     - 按照各云平台的容器服务文档进行部署
     - 可以配置从GitHub或Gitee仓库自动构建和部署

### 注意事项
- Docker容器化部署提供更好的隔离性和可移植性
- 需要配置合适的资源（CPU、内存）
- 建议使用CI/CD工具自动化构建和部署流程

## 部署方案四：云服务器手动部署

使用传统的云服务器手动部署，适合需要更多控制权的场景。

### 部署步骤

1. **购买云服务器**
   - 推荐平台：AWS EC2、阿里云ECS、腾讯云CVM
   - 操作系统：Ubuntu 22.04 LTS
   - 配置建议：2核4G以上，至少20GB磁盘空间

2. **连接服务器**
   ```bash
   ssh ubuntu@your-server-ip
   ```

3. **安装依赖**
   ```bash
   # 更新系统
   sudo apt-get update && sudo apt-get upgrade -y
   
   # 安装Python 3.11
   sudo apt-get install -y python3.11 python3.11-venv python3.11-dev
   
   # 安装Chrome浏览器
   sudo apt-get install -y wget gnupg2 unzip
   wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | sudo apt-key add -
   sudo sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list'
   sudo apt-get update
   sudo apt-get install -y google-chrome-stable
   
   # 安装ChromeDriver
   CHROME_VERSION=$(google-chrome --version | grep -oP "\d+\.\d+\.\d+")
   wget -O chromedriver.zip https://storage.googleapis.com/chrome-for-testing-public/$CHROME_VERSION/linux64/chromedriver-linux64.zip
   unzip chromedriver.zip
   sudo mv chromedriver-linux64/chromedriver /usr/local/bin/
   sudo chmod +x /usr/local/bin/chromedriver
   ```

4. **部署应用**
   ```bash
   # 创建项目目录
   mkdir -p ~/ecommerce-analysis
   cd ~/ecommerce-analysis
   
   # 克隆项目（选择一个）
   # 从GitHub克隆
   git clone https://github.com/your-username/your-repo.git .
   
   # 或从Gitee克隆
   git clone https://gitee.com/your-username/your-repo.git .
   
   # 创建虚拟环境
   python3.11 -m venv venv
   source venv/bin/activate
   
   # 安装依赖
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

5. **配置环境变量**
   ```bash
   # 创建.env文件
   nano .env
   
   # 添加环境变量
   ALIYUN_API_KEY=your_api_key
   
   # 保存并退出
   ```

6. **启动应用**
   ```bash
   # 直接启动（适合测试）
   streamlit run app.py
   
   # 使用nohup后台运行
   nohup streamlit run app.py > streamlit.log 2>&1 &
   
   # 使用systemd管理（推荐）
   sudo nano /etc/systemd/system/streamlit.service
   ```

7. **配置systemd服务**
   ```ini
   [Unit]
   Description=Streamlit Ecommerce Analysis App
   After=network.target
   
   [Service]
   User=ubuntu
   WorkingDirectory=/home/ubuntu/ecommerce-analysis
   Environment="PATH=/home/ubuntu/ecommerce-analysis/venv/bin"
   ExecStart=/home/ubuntu/ecommerce-analysis/venv/bin/streamlit run app.py
   Restart=always
   
   [Install]
   WantedBy=multi-user.target
   ```

8. **启动并启用服务**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl start streamlit
   sudo systemctl enable streamlit
   
   # 查看服务状态
   sudo systemctl status streamlit
   ```

### 注意事项
- 需要配置防火墙规则，允许8501端口访问
- 建议使用域名并配置HTTPS（可使用Let's Encrypt免费证书）
- 定期备份数据和代码

## 部署方案比较

| 部署方案 | 难度 | 成本 | 灵活性 | 维护量 | 推荐指数 |
|---------|------|------|--------|--------|----------|
| Streamlit Cloud | 简单 | 免费/付费 | 低 | 低 | ⭐⭐⭐⭐⭐ |
| Heroku | 中等 | 免费/付费 | 中 | 中 | ⭐⭐⭐⭐ |
| Docker容器化 | 中等 | 按需付费 | 高 | 中 | ⭐⭐⭐⭐ |
| 云服务器手动部署 | 复杂 | 按需付费 | 很高 | 高 | ⭐⭐⭐ |

## 部署注意事项

### 1. 环境变量配置
- 不要将敏感信息（如API Key）硬编码到代码中
- 使用环境变量或配置文件管理敏感信息
- 部署时重新配置.env文件或在云平台控制台设置环境变量

### 2. 依赖管理
- 确保requirements.txt包含所有必要依赖
- 建议固定依赖版本，避免版本冲突
- 使用虚拟环境隔离不同项目的依赖

### 3. 爬虫功能注意事项
- 云端部署时，Selenium可能需要额外配置
- 确保Chrome浏览器和ChromeDriver版本匹配
- 考虑使用无头浏览器模式：`options.add_argument('--headless')`
- 频繁爬取可能导致IP被封禁，建议使用代理或控制爬取频率

### 4. 性能优化
- 优化爬虫代码，减少内存占用
- 合理设置并发数，避免服务器资源过载
- 考虑使用缓存机制，减少重复爬取

### 5. 监控和日志
- 配置日志记录，便于排查问题
- 使用监控工具（如Prometheus + Grafana）监控应用状态
- 设置告警机制，及时发现和处理异常

## 常见问题排查

1. **应用无法启动**
   - 检查端口是否被占用：`netstat -tuln | grep 8501`
   - 查看日志文件：`tail -f streamlit.log`
   - 检查依赖是否安装正确：`pip list`

2. **爬虫功能无法正常工作**
   - 检查Chrome浏览器和ChromeDriver版本是否匹配
   - 确保ChromeDriver可执行：`which chromedriver`
   - 检查网络连接和代理设置
   - 查看爬虫日志，排查具体错误

3. **AI分析功能无法使用**
   - 检查openai模块是否安装：`pip list | grep openai`
   - 检查API Key是否正确配置
   - 查看API调用日志，排查具体错误

4. **应用访问缓慢**
   - 检查服务器资源使用情况：`top`或`htop`
   - 优化代码，减少不必要的计算和网络请求
   - 考虑升级服务器配置或使用CDN加速

## 更新部署

### 1. Streamlit Cloud
- 直接推送代码到GitHub仓库，应用会自动更新

### 2. Heroku
- 推送代码到Heroku remote：`git push heroku main`

### 3. Docker容器化
- 重新构建镜像：`docker build -t ecommerce-analysis .`
- 停止并删除旧容器：`docker stop <container-id> && docker rm <container-id>`
- 运行新容器：`docker run -d -p 80:8501 ecommerce-analysis`

### 4. 云服务器手动部署
- 进入项目目录：`cd ~/ecommerce-analysis`
- 拉取最新代码：`git pull`
- 重启应用：
  - 如果使用nohup：停止旧进程并重新启动
  - 如果使用systemd：`sudo systemctl restart streamlit`

## 总结

根据您的技术水平和需求，可以选择不同的部署方案：
- 初学者推荐使用Streamlit Cloud，部署简单快捷
- 有一定经验的用户可以选择Heroku或Docker容器化部署
- 需要更多控制权和自定义配置的用户可以选择云服务器手动部署

无论选择哪种部署方案，都需要注意环境配置、依赖管理和安全问题。祝您部署顺利！

## 联系我们

如果您在部署过程中遇到问题，欢迎联系项目维护者寻求帮助。
