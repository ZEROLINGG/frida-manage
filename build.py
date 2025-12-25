#!/user/bin/env python3
import logging
import lzma
import os
from pathlib import Path
import shutil
import threading
import zipfile
import concurrent.futures
import json
import re

import requests

# ================= 配置路径 =================
# 使用 Pathlib 获取当前脚本所在的目录作为基准路径
PATH_BASE = Path(__file__).parent.resolve()
# 模块模板目录（包含 service.sh, module.prop 等基础文件）
PATH_BASE_MODULE: Path = PATH_BASE.joinpath("base")
# 构建输出目录
PATH_BUILD: Path = PATH_BASE.joinpath("build")
# 构建过程中的临时目录
PATH_BUILD_TMP: Path = PATH_BUILD.joinpath("tmp")
# 下载缓存目录，用于存放下载的 frida-server 压缩包
PATH_DOWNLOADS: Path = PATH_BASE.joinpath("downloads")

# ================= 日志设置 =================
logger = logging.getLogger()
syslog = logging.StreamHandler()
# 日志格式：包含线程名称（因为后面使用了多进程/多线程），方便调试
formatter = logging.Formatter("%(threadName)s : %(message)s")
syslog.setFormatter(formatter)
logger.setLevel(logging.INFO)
logger.addHandler(syslog)


def download_file(url: str, path: Path):
    """
    通用下载函数
    :param url: 下载链接
    :param path: 本地保存路径
    """
    # 从 URL 中截取文件名用于显示日志
    file_name = url[url.rfind("/") + 1 :]
    logger.info(f"Downloading '{file_name}' to '{path}'")

    # 如果文件已存在，则跳过下载（缓存机制）
    if path.exists():
        return

    # 发起请求，允许重定向
    r = requests.get(url, allow_redirects=True)
    # 如果状态码不是 200，抛出异常
    r.raise_for_status()
    # 以二进制写模式保存文件
    with open(path, "wb") as f:
        f.write(r.content)

    logger.info("Done")


def extract_file(archive_path: Path, dest_path: Path):
    """
    解压 .xz 文件的函数
    :param archive_path: 压缩包路径 (.xz)
    :param dest_path: 解压后的目标文件路径
    """
    logger.info(f"Extracting '{archive_path.name}' to '{dest_path.name}'")

    # 使用 lzma 库打开 .xz 压缩包
    with lzma.open(archive_path) as f:
        file_content = f.read() # 读取解压后的数据
        path = dest_path.parent

        # 确保目标目录存在
        path.mkdir(parents=True, exist_ok=True)

        # 将解压后的数据写入目标文件
        with open(dest_path, "wb") as out:
            out.write(file_content)


def generate_version_code(project_tag: str) -> int:
    """
    将版本号字符串转换为整数，用于 Android 的 versionCode
    例如: "16.1.4" -> 160104
    """
    # 按 "." 或 "-" 分割版本号
    parts = re.split("[-.]", project_tag)
    # 将每部分转为整数并补零至2位，然后拼接
    version_code = "".join(f"{int(part):02d}" for part in parts)
    return int(version_code)


def create_module_prop(path: Path, project_tag: str):
    """
    生成 Magisk 模块必须的 module.prop 文件
    """
    # 定义文件内容，注意这里包含硬编码的 updateJson URL，
    # 如果你是 Fork 的项目，这里通常需要修改为自己的仓库地址
    module_prop = f"""id=magisk-frida
name=MagiskFrida
version={project_tag}
versionCode={generate_version_code(project_tag)}
author=ViRb3 & enovella
updateJson=https://github.com/ViRb3/magisk-frida/releases/latest/download/updater.json
description=Run frida-server on boot"""

    # 写入文件
    with open(path.joinpath("module.prop"), "w", newline="\n") as f:
        f.write(module_prop)


def create_module(project_tag: str):
    """
    初始化模块构建环境
    """
    logger.info("Creating module")

    # 如果临时目录存在，先删除，确保干净的构建环境
    if PATH_BUILD_TMP.exists():
        shutil.rmtree(PATH_BUILD_TMP)

    # 将 base 目录下的所有模板文件复制到临时构建目录
    shutil.copytree(PATH_BASE_MODULE, PATH_BUILD_TMP)
    # 生成 prop 文件
    create_module_prop(PATH_BUILD_TMP, project_tag)


def fill_module(arch: str, frida_tag: str, project_tag: str):
    """
    【核心工作函数】下载并填充特定架构的 Frida Server
    此函数会被多进程并发调用
    :param arch: 架构名称 (如 arm64, x86)
    :param frida_tag: Frida 的版本号 (如 16.1.4)
    :param project_tag: 项目版本号
    """
    # 设置当前线程/进程名称，方便日志区分是哪个架构正在下载
    threading.current_thread().setName(arch)
    logger.info(f"Filling module for arch '{arch}'")

    # 构造 GitHub 下载链接
    frida_download_url = (
        f"https://github.com/frida/frida/releases/download/{frida_tag}/"
    )
    # 构造文件名: frida-server-16.1.4-android-arm64.xz
    frida_server = f"frida-server-{frida_tag}-android-{arch}.xz"
    frida_server_path = PATH_DOWNLOADS.joinpath(frida_server)

    # 1. 下载文件到 downloads 目录
    download_file(frida_download_url + frida_server, frida_server_path)

    # 准备解压目录：build/tmp/files
    # 注意：这里并不是放入 system/bin，而是放入 files 目录，
    # 意味着这是一个 "All-in-One" 包，安装时脚本会从 files 里挑对应的文件
    files_dir = PATH_BUILD_TMP.joinpath("files")
    files_dir.mkdir(exist_ok=True)

    # 2. 解压文件并重命名为 frida-server-arm64
    extract_file(frida_server_path, files_dir.joinpath(f"frida-server-{arch}"))


def create_updater_json(project_tag: str):
    """
    生成 updater.json，用于 Magisk 管理器检测更新
    """
    logger.info("Creating updater.json")

    updater = {
        "version": project_tag,
        "versionCode": generate_version_code(project_tag),
        "zipUrl": f"https://github.com/ViRb3/magisk-frida/releases/download/{project_tag}/MagiskFrida-{project_tag}.zip",
        "changelog": "https://raw.githubusercontent.com/ViRb3/magisk-frida/master/CHANGELOG.md",
    }

    # 写入 json 文件，格式化缩进为 4 空格
    with open(PATH_BUILD.joinpath("updater.json"), "w", newline="\n") as f:
        f.write(json.dumps(updater, indent=4))


def package_module(project_tag: str):
    """
    将构建好的临时目录打包成 .zip 文件
    """
    logger.info("Packaging module")

    # 最终 zip 文件的路径
    module_zip = PATH_BUILD.joinpath(f"MagiskFrida-{project_tag}.zip")

    # 创建 zip 文件，使用 DEFLATED 压缩算法
    with zipfile.ZipFile(module_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 遍历临时目录下的所有文件
        for root, _, files in os.walk(PATH_BUILD_TMP):
            for file_name in files:
                # 排除占位文件和 git 配置文件
                if file_name == "placeholder" or file_name == ".gitkeep":
                    continue
                # 将文件写入 zip 包
                zf.write(
                    Path(root).joinpath(file_name), # 源文件路径
                    # 在 zip 包内的相对路径
                    arcname=Path(root).relative_to(PATH_BUILD_TMP).joinpath(file_name),
                )

    # 打包完成后删除临时构建目录
    shutil.rmtree(PATH_BUILD_TMP)


def do_build(frida_tag: str, project_tag: str):
    """
    【主入口函数】执行完整的构建流程
    """
    # 确保目录存在
    PATH_DOWNLOADS.mkdir(parents=True, exist_ok=True)
    PATH_BUILD.mkdir(parents=True, exist_ok=True)

    # 1. 创建模块骨架
    create_module(project_tag)

    # 定义需要下载的架构列表
    archs = ["arm", "arm64", "x86", "x86_64"]

    # 2. 并发下载与处理
    # 使用进程池执行器 (ProcessPoolExecutor) 来并行处理任务
    # 这会同时启动 4 个进程，分别下载不同架构的文件，大大加快速度
    executor = concurrent.futures.ProcessPoolExecutor()
    futures = [
        # 提交任务给进程池: fill_module(arch, frida_tag, project_tag)
        executor.submit(fill_module, arch, frida_tag, project_tag) for arch in archs
    ]

    # 等待所有任务完成，并捕获可能的异常
    for future in concurrent.futures.as_completed(futures):
        if future.exception() is not None:
            raise future.exception()

    # 3. 打包 zip
    package_module(project_tag)

    # 4. 生成更新信息
    create_updater_json(project_tag)

    logger.info("Done")