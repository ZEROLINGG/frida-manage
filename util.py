import re
import requests
import subprocess


# ================= 版本号处理工具 =================

# 将带修订号的版本 tag 还原为基础版本
# 例如: 输入 "12.7.5-2" -> 输出 "12.7.5"
# 逻辑: 以第一个 '-' 为界限分割字符串，取前半部分
def strip_revision(tag) -> str:
    return tag.split('-', 1)[0]


# ================= GitHub API 交互 =================

# 获取指定 GitHub 仓库的最新发布 (Release) Tag
# 参数 project_name: 格式为 "owner/repo"，例如 "frida/frida"
def get_last_github_tag(project_name) -> str:
    # GitHub 官方 API 地址
    releases_url = f"https://api.github.com/repos/{project_name}/releases/latest"

    # 发送 HTTP GET 请求
    r = requests.get(releases_url)
    # 如果响应状态码不是 200 (例如 404 或 403 限流)，则抛出异常
    r.raise_for_status()

    releases = r.json()
    # TODO: 这里假设 API 返回的 'tag_name' 就是最新的，
    # 实际上 GitHub API 的 /latest 接口确实返回最新的正式版（非 Pre-release）
    last_release = releases["tag_name"]
    return last_release


# 封装函数：专门获取 frida/frida 官方仓库的最新版本 Tag
def get_last_frida_tag() -> str:
    last_frida_tag = get_last_github_tag('frida/frida')
    print(f"Last frida tag: {last_frida_tag}")
    return last_frida_tag


# ================= 本地 Git 仓库操作 =================

# 获取当前项目（本地 Git）的最新 Tag
# 它是基于 get_last_tag 实现的
def get_last_project_tag() -> str:
    last_tag = get_last_tag([])
    print(f"Last project tag: {last_tag}")
    return last_tag


# 对版本号列表进行自然排序（Semantic Versioning 排序）
# 为什么需要这个函数？
# 因为默认的字符串排序中 "1.10" 会排在 "1.2" 前面 (字符串比较)。
# 这个函数将版本号拆分为数字列表 [1, 10] 和 [1, 2]，从而正确识别 1.10 > 1.2
def sort_tags(tags: [str]) -> [str]:
    tags = tags.copy()
    s: str
    # key=lambda... : 定义排序规则
    # re.split(r"[\.-]", s): 按 '.' 或 '-' 分割字符串
    # map(int, ...): 将分割后的部分转为整数，以便进行数值比较
    tags.sort(key=lambda s: list(map(int, re.split(r"[\.-]", s))))
    return tags


# 获取符合特定过滤条件的最新 Tag
# 参数 filter_args: 传递给 git tag -l 的参数，例如匹配模式
def get_last_tag(filter_args: [str]) -> str:
    # 1. 执行 git tag -l 获取所有 tag
    # 2. splitlines() 将结果按行分割成列表
    tags = exec_git_command(["tag", "-l"] + filter_args).splitlines()

    # 如果没有找到 tag，返回空字符串
    # 否则，调用 sort_tags 进行正确排序，并取最后一个（最大的版本号）
    last_tag = "" if len(tags) < 1 else sort_tags(tags)[-1]
    return last_tag


# 执行系统 Git 命令的底层封装
# 参数 command_with_args: 命令列表，例如 ["tag", "-l"]
def exec_git_command(command_with_args: [str]) -> str:
    # subprocess.run 用于执行外部命令
    # capture_output=True 表示捕获标准输出和错误输出
    result = subprocess.run(["git"] + command_with_args,
                            capture_output=True).stdout
    # 将 bytes 解码为 string 返回
    return result.decode()


# 计算下一个版本号（修订号递增逻辑）
# 如果当前 Frida 版本是 12.7.5
# 它会依次检查 12.7.5-1, 12.7.5-2 是否已存在
# 直到找到一个未被占用的 tag
def get_next_revision(current_tag: str) -> str:
    i = 1
    while True:
        new_tag = f"{current_tag}-{i}"
        # 检查这个 tag 是否存在于本地 git 仓库
        if get_last_tag([new_tag]) == '':
            # 如果 get_last_tag 返回空，说明这个 tag 还没人用，可以使用
            break
        i += 1
    return new_tag