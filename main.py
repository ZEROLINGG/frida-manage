import build
import util
import os


def main():
    # 1. 获取版本信息
    # 获取 Frida 官方仓库的最新 Tag (例如: "16.1.4")
    last_frida_tag = util.get_last_frida_tag()
    # 获取本项目(MagiskFrida)git 仓库中最新的 Tag (例如: "16.1.3-1")
    last_project_tag = util.get_last_project_tag()

    # 初始化新版本号变量，默认为 "0" (如果没有更新，这个值不会被真正使用)
    new_project_tag = "0"

    # 2. 检查触发条件
    # 检查环境变量 FORCE_RELEASE 是否为 true (通常在 GitHub Actions 中手动设置以强制重新构建)
    force_release = os.getenv('FORCE_RELEASE', 'false').lower() == 'true'

    # 核心判断逻辑：
    # 如果 Frida 官方版本 != 本项目基础版本 (去掉 -1, -2 这种修订号后的版本)
    # 例如：官方是 "16.1.4"，本项目是 "16.1.3"，则需要更新
    needs_update = last_frida_tag != util.strip_revision(last_project_tag)

    # 3. 决策流程
    if needs_update or force_release:
        # 计算下一个版本号
        # 逻辑：如果当前 Tag 是 16.1.4-1，它会生成 16.1.4-2
        # 如果是全新的 Frida 版本，它会生成 16.1.4-1
        new_project_tag = util.get_next_revision(last_frida_tag)
        print(f"Update needed to {new_project_tag}")

        # 打印更新原因，方便日志排查
        if needs_update:
            print(f"Reason: Frida updated from {util.strip_revision(last_project_tag)} to {last_frida_tag}")
        else:
            print("Reason: Force release requested via GitHub Actions")

        # 【关键步骤】写入标记文件
        # 将新版本号写入 NEW_TAG.txt
        # GitHub Actions 的后续步骤(Workflow)会读取这个文件
        # 如果这个文件存在，CI 就会给 Git 仓库打上这个 Tag 并发布 Release
        with open("NEW_TAG.txt", "w") as the_file:
            the_file.write(new_project_tag)
    else:
        # 如果不需要更新，且没有强制发布
        print("All good!")

    # 4. 执行构建
    # 调用 build.py 里的 do_build 函数真正开始下载和打包
    # 注意：如果不需要更新，这里传入的 new_project_tag 是 "0"，
    # 这通常意味着在本地测试或者非发布状态下，只跑一遍流程但不生成有效 Release
    build.do_build(last_frida_tag, new_project_tag)


if __name__ == "__main__":
    main()