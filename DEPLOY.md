# 部署指南（5 分钟）

## 第 1 步：推代码到 GitHub

在你的终端里跑这几条命令：

```bash
cd "/Users/mathewm/Documents/NUS/Y1S1/GET1008 public speaking/video-quiz-app"
git init
git add .
git commit -m "Initial commit: Video Notes app"
```

然后在 GitHub 上创建一个新仓库（公开或私有都行），名字叫 `video-notes`。GitHub 会给你三条命令，直接跑就行：

```bash
git remote add origin https://github.com/你的用户名/video-notes.git
git branch -M main
git push -u origin main
```

## 第 2 步：部署到 Streamlit Community Cloud

1. 打开 https://share.streamlit.io
2. 用你的 GitHub 账号登录
3. 点 **New app**
4. 选你的 `video-notes` 仓库
5. **Main file path** 填 `app.py`
6. 点 **Deploy**

部署完成后会给你一个永久链接，类似：
`https://menxuanmo-video-notes.streamlit.app`

## 第 3 步：设置 Secrets（保护 API key）

部署好后，在 Streamlit 控制台：
1. 点右上角 **⚙️ Settings**
2. 找到 **Secrets** 区域
3. 填入以下内容：

```toml
DEEPSEEK_API_KEY = "你的 API key"
```

保存后刷新页面，就能用了。

## 安全注意事项

- `.gitignore` 已经配置了 `.streamlit/secrets.toml` 不会被提交到 GitHub
- 你的 API key 只在 Streamlit 云端的 Secrets 里，代码仓库里看不到
- 如果想保护额度，可以在 DeepSeek 控制台设置月度限额
