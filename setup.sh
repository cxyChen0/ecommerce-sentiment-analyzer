#!/bin/bash
set -e

# 电商智能选品分析系统部署脚本

# 1. 安装Python依赖
echo "🔧 安装Python依赖..."
pip install --no-cache-dir -r requirements.txt

# 2. 设置环境变量
echo "⚙️ 设置环境变量..."
export STREAMLIT_SERVER_PORT=8501
export STREAMLIT_SERVER_ADDRESS=0.0.0.0
export STREAMLIT_SERVER_HEADLESS=true
export STREAMLIT_SERVER_ENABLE_CORS=false
export STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false
export PYTHONPATH=$PYTHONPATH:.

# 3. 创建必要的目录
echo "📁 创建必要的目录..."
mkdir -p D:\Login_dataset\SeleniumUserData_1
mkdir -p D:\Login_dataset\SeleniumUserData_2
mkdir -p D:\Login_dataset\SeleniumUserData_3
mkdir -p D:\Login_dataset\SeleniumUserData_Search

# 4. 提示部署完成
echo "🎉 部署完成！"
echo "🚀 运行命令: streamlit run app.py"
echo "🌐 访问地址: http://localhost:8501"