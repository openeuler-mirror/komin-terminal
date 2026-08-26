# Komin-Terminal

## 软件介绍

**Komin-Terminal** 是面向 Linux 系统管理员的 AI 驱动命令行智能助手。用户在终端中以自然语言提问，即可获得系统管理相关的 AI 解答，全程不离开命令行。

架构上采用 **CLI 客户端（`km` / `komin`）+ 守护进程（`komind`）双层设计**，经 **D-Bus 系统总线**通信：守护进程负责与客户自配置的 OpenAI 兼容 API 通信并持久化数据，CLI 负责交互与渲染。

```
km / komin ──D-Bus 系统总线──> komind ──HTTPS──> OpenAI 兼容 API
                                  │
                                  └── SQLite/MySQL/PostgreSQL（历史记录）
```

### 核心功能

| 功能 | 说明 |
|------|------|
| 单次问答 | 一条命令直接获得 AI 解答，流式输出 + Markdown 终端渲染 |
| 交互会话 | 命名会话的多轮对话，支持创建/列出/切换/删除 |
| 历史管理 | 问答历史持久化，关键词过滤、分页、软删除与恢复 |
| 终端捕获 | 录制交互 shell 会话，输出可作为问答上下文 |
| 管道集成 | `命令输出 \| km` 自动并入上下文，可无显式问题直接提问 |
| 文件附件 | 将文本文件作为上下文附加给 AI（单个 ≤ 1 MiB） |

## 目录与分类

```
komin/
├── komin_terminal/              # 主包（Python 源码）
│   ├── commands/                #   CLI 命令层：入口路由、chat、history、shell
│   ├── config/                  #   配置管理：YAML 加载、校验、默认值
│   ├── daemon/                  #   守护进程：komind 入口、会话身份
│   │   ├── database/            #     数据库层：引擎管理、ORM 模型、仓库模式
│   │   └── http/                #     HTTP 层：OpenAI 请求、重试、SSE 流解析
│   ├── dbus/                    #   D-Bus 通信：总线抽象、接口、结构、客户端
│   ├── rendering/               #   终端渲染：Markdown→ANSI、主题、流式、动画
│   ├── terminal/                #   终端捕获：PTY 录制、输出清洗
│   ├── utils/                   #   工具：XDG 路径、文件锁、计时
│   ├── constants.py             #   全局常量（D-Bus 命名空间、FHS 路径）
│   ├── exceptions.py            #   异常层次
│   └── logger.py                #   日志与审计（journald，自动降级 stderr）
├── data/
│   ├── release/                 # 发布部署产物：systemd 单元、D-Bus 策略、
│   │                            #   SELinux 策略、man 页、示例配置
│   └── development/             # 开发态配置（vendor=example）
├── packaging/                   # RPM SPEC（komin-terminal.spec）
├── scripts/                     # prepare_release.py 等构建辅助脚本
├── tests/                       # 与主包同构的离线测试（735 用例）
├── docs/                        # 架构设计
└── pyproject.toml / Makefile
```

## CLI 示例

```bash
# 单次问答（流式输出 + Markdown 渲染）
km "如何配置 firewalld 允许 HTTP 流量？"

# 管道输入：命令输出作为上下文
journalctl -u nginx -n 50 | km "分析这些日志中的错误"

# 管道输入：无显式问题，管道内容即问题
echo "如何查看系统负载？" | km

# 文件附件
km chat -a /etc/nginx/nginx.conf "解释这个配置文件的作用"

# 交互式多轮会话
km chat -i --name "磁盘故障排查" --description "排查 /var 空间不足"
#   会话内建命令：/exit /quit /list /model <模型> /help

# 会话管理
km chat --list
km chat --switch <CHAT_ID>
km chat --delete <CHAT_ID>

# 历史管理
km history                                # 分页列表
km history --filter "SELinux"             # 关键词过滤
km history --since 2026-08-01 --until 2026-08-25
km history --clear                        # 清除（软删除，需确认；--yes 跳过）
km history --restore <ID>                 # 恢复软删记录

# 终端捕获
km shell --enable-record                  # 录制交互 shell 会话
km shell --show-last                      # 查看最近录制（清洗 ANSI 后）
km --with-output "分析刚才的终端输出"      # 最近录制作为问答上下文

# 全局选项
km --version
km --model <模型> "问题"                   # 指定本次模型
km --no-spinner "问题"                    # 禁用加载动画
km --debug "问题"                         # 调试日志
```

## 环境要求

| 项 | 要求 |
|----|------|
| 操作系统 | 仅 Linux（x86_64 / aarch64），需 systemd 与 D-Bus 系统总线 |
| Python | ≥ 3.11 |
| 运行依赖 | dasbus ≥ 1.7、pygobject、httpx ≥ 0.27、SQLAlchemy ≥ 1.4.45（< 2.0）、PyYAML ≥ 6.0、markdown ≥ 3.5 |
| 发行版包名 | `python3-dasbus`、`python3-gobject`、`python3-httpx`、`python3-sqlalchemy`、`python3-pyyaml`、`python3-markdown` |
| 构建依赖（RPM） | `python3-devel`、`python3-setuptools`、`python3-wheel`、`python3-build`、`python3-pip`、`python3-pytest` 及全部运行依赖 |
| AI 后端 | 任意 OpenAI 兼容 API（OpenAI / DeepSeek / vLLM / Ollama 等），由配置文件指定 |

## 安装和验证

### 配置文件（必需）

配置按 **系统级 → 用户级** 合并（用户级优先）：

- 系统级：`/etc/komin/config.yaml`（RPM 安装，占位密钥）
- 用户级：`~/.config/komin/config.yaml`（建议 `chmod 600`）

最小可用配置：

```yaml
backend:
  url: "https://你的端点/v1"     # OpenAI 兼容 API 地址
  api_key: "sk-..."              # API 密钥
  model: "你的默认模型"
```

### 方式一：RPM 安装（生产）

```bash
# 1. 构建（在仓库根目录；自动创建 rpmbuild 目录树、git archive 打包源码并 rpmbuild 构建）
make build

# 2. 安装（主包 + 数据包 + 帮助包，经 dnf 解决依赖）
make install

# 3. 启动守护进程（systemd 管理，Type=dbus 激活）
systemctl start komind
systemctl enable komind          # 可选：开机自启
```

> 构建期 `prepare_release.py` 会把部署模板中的 `{vendor}` 替换为发行版 vendor（如 openEuler → `openeuler`），并把该 vendor 烘焙进安装包，客户端与守护进程默认使用同一 D-Bus 命名空间。

### 方式二：开发安装（源码）

```bash
python3 -m venv .venv
source .venv/bin/activate
make install-dev                 # 可编辑安装 + 开发依赖
```

开发态默认 vendor 为 `example`（`com.example.komin.*`），可用 `KOMIN_DBUS_VENDOR` 覆盖；以 `komind --debug` 前台启动即可调试。

### 验证

```bash
# 1. 版本与守护进程
km --version                     # 输出 km 1.0.0
komind --version                 # 输出 komin-terminal 1.0.0
systemctl status komind          # active (running)

# 2. 真实问答（流式渲染）
km "如何查看系统负载？"

# 3. 历史落库
km history                       # 应能看到上一步的问答记录

# 4. 审计日志（journald）
journalctl -t komind -n 5        # backend.request JSON 审计事件

# 开发自检
make check                       # ruff + mypy strict + 735 测试
```

### 常用 make 目标

| 目标 | 说明 |
|------|------|
| `make install-dev` | 以可编辑模式安装项目及全部开发依赖 |
| `make build` | rpmbuild 构建 RPM（主包 + data + help 子包） |
| `make install` | dnf 安装已构建的全部子包（不触发编译） |
| `make remove` | 卸载已安装的全部 komin-terminal 子包 |
| `make test` | 运行 pytest 测试 |
| `make test-cov` | 运行测试并输出覆盖率 |
| `make lint` | ruff 代码检查 |
| `make format` | ruff 自动格式化与修复 |
| `make typecheck` | mypy 严格类型检查 |
| `make check` | 依次执行 lint、typecheck、test |
| `make clean` | 清理构建与缓存产物 |

## 文档索引

- [架构设计](docs/komin-terminal-架构设计.md)

## 许可证

[Apache License 2.0](LICENSE)
