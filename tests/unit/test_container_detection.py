"""Container detection and the mount layout get_mount_config() derives from it.

Every case builds a fake filesystem root under tmp_path, so the real host's
/cache, /data or docker mounts never decide the result.
"""

import functools
import tempfile
from pathlib import Path

import pytest

import scalo.config.config as cfg

DOCKER_ID = "0ddaeccc84c6fcf3cadf246caa3f5a6578f505691c1923b1517a23b4a3107959"

# A bare-metal host running docker: ext4 root, with the containers' overlays and netns mounts listed beside it.
DOCKER_HOST_MOUNTINFO = (
    "27 1 8:1 / / rw,relatime shared:1 - ext4 /dev/sda1 rw,errors=remount-ro\n"
    "176 27 8:17 / /cache rw,relatime shared:94 - ext4 /dev/sdb1 rw\n"
    f"423 176 0:65 / /cache/docker/rootfs/overlayfs/{DOCKER_ID} rw,relatime shared:220 - overlay overlay "
    "rw,lowerdir=/cache/docker/containerd/daemon/io.containerd.snapshotter.v1.overlayfs/snapshots/12/fs,"
    "upperdir=/cache/docker/containerd/daemon/io.containerd.snapshotter.v1.overlayfs/snapshots/13/fs\n"
    "439 34 0:5 net:[4026533674] /run/docker/netns/026949dfeea6 rw shared:225 - nsfs nsfs rw\n"
)

# Inside a docker container: the root mount is the overlay docker assembled.
CONTAINER_MOUNTINFO = (
    "612 540 0:61 / / rw,relatime master:220 - overlay overlay "
    "rw,lowerdir=/var/lib/docker/overlay2/l/ABC:/var/lib/docker/overlay2/l/DEF,"
    "upperdir=/var/lib/docker/overlay2/123/diff,workdir=/var/lib/docker/overlay2/123/work\n"
    "613 612 0:64 / /proc rw,nosuid,nodev,noexec,relatime - proc proc rw\n"
)

# An image-based desktop distro whose root is a composefs overlay that no container runtime built.
COMPOSEFS_MOUNTINFO = (
    "28 1 0:31 / / ro,relatime shared:1 - overlay composefs "
    "ro,lowerdir+=/run/ostree/.private/cfsroot-lower,datadir+=/sysroot/ostree/repo/objects\n"
)

HOST_PID1_CGROUP = "0::/init.scope\n"
HOST_SELF_CGROUP = "0::/user.slice/user-1000.slice/user@1000.service/app.slice/terminal.scope\n"


@pytest.fixture(autouse=True)
def _no_container_env(monkeypatch):
    """Clear the env vars that would short-circuit detection, e.g. on a CI runner that is a pod."""
    for var in ("KUBERNETES_SERVICE_HOST", "container", "DOCKER_CONTAINER", "ECS_CONTAINER_METADATA_URI"):
        monkeypatch.delenv(var, raising=False)


def _fake_root(
    root: Path,
    *,
    mountinfo: str = DOCKER_HOST_MOUNTINFO,
    pid1_cgroup: str = HOST_PID1_CGROUP,
    self_cgroup: str = HOST_SELF_CGROUP,
) -> Path:
    """Write the /proc files the detector reads under ``root``."""
    (root / "proc/1").mkdir(parents=True)
    (root / "proc/self").mkdir(parents=True)
    (root / "proc/1/cgroup").write_text(pid1_cgroup, encoding="utf-8")
    (root / "proc/self/cgroup").write_text(self_cgroup, encoding="utf-8")
    (root / "proc/self/mountinfo").write_text(mountinfo, encoding="utf-8")
    return root


class TestHostIsNotAContainer:
    """A bare-metal host is local, whatever generic paths or container mounts it has."""

    def test_docker_host_with_cache_and_data_dirs(self, tmp_path):
        root = _fake_root(tmp_path)
        for generic in ("cache", "data", "app/config", "config"):
            (root / generic).mkdir(parents=True)

        assert cfg._is_container(root) == (False, "none")

    def test_composefs_overlay_root(self, tmp_path):
        root = _fake_root(tmp_path, mountinfo=COMPOSEFS_MOUNTINFO)

        assert cfg._is_container(root) == (False, "none")

    @pytest.mark.parametrize(
        "cgroup",
        [
            "0::/system.slice/containerd.service\n",
            "0::/system.slice/docker.service\n",
            "0::/user.slice/user-1000.slice/user@1000.service/app.slice/app-docker\\x2ddesktop-1234.scope\n",
            "0::/system.slice/docker-backup.service\n",
        ],
    )
    def test_host_service_cgroups(self, tmp_path, cgroup):
        root = _fake_root(tmp_path, self_cgroup=cgroup)

        assert cfg._is_container(root) == (False, "none")

    def test_detect_environment_on_docker_host(self, tmp_path, monkeypatch):
        root = _fake_root(tmp_path)
        monkeypatch.setattr(cfg, "_is_container", functools.partial(cfg._is_container, root))

        assert cfg.detect_environment() == "bare_metal"


class TestContainerEvidence:
    """Each kind of container evidence is detected on its own."""

    def test_overlay_root_built_by_docker(self, tmp_path):
        root = _fake_root(tmp_path, mountinfo=CONTAINER_MOUNTINFO, pid1_cgroup="0::/\n", self_cgroup="0::/\n")

        assert cfg._is_container(root) == (True, "mountinfo")

    def test_dockerenv(self, tmp_path):
        root = _fake_root(tmp_path)
        (root / ".dockerenv").touch()

        assert cfg._is_container(root) == (True, "dockerenv")

    def test_k8s_serviceaccount(self, tmp_path):
        root = _fake_root(tmp_path)
        (root / "var/run/secrets/kubernetes.io/serviceaccount").mkdir(parents=True)

        assert cfg._is_container(root) == (True, "k8s_serviceaccount")

    def test_kubernetes_service_host(self, tmp_path, monkeypatch):
        root = _fake_root(tmp_path)
        monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.0.0.1")

        assert cfg._is_container(root) == (True, "kubernetes")

    @pytest.mark.parametrize(
        "cgroup",
        [
            f"12:memory:/docker/{DOCKER_ID}\n",
            f"0::/system.slice/docker-{DOCKER_ID}.scope\n",
            "0::/kubepods.slice/kubepods-burstable.slice/kubepods-burstable-pod1.slice/cri-containerd-1.scope\n",
            "11:devices:/kubepods/besteffort/pod1/abc\n",
            "11:devices:/lxc/web01\n",
        ],
    )
    def test_container_cgroups(self, tmp_path, cgroup):
        root = _fake_root(tmp_path, pid1_cgroup=cgroup)

        assert cfg._is_container(root) == (True, "cgroups_cgroup")

    def test_container_env_var(self, tmp_path, monkeypatch):
        root = _fake_root(tmp_path)
        monkeypatch.setenv("container", "podman")

        assert cfg._is_container(root) == (True, "env_container")


class TestLocalMountLayout:
    """On bare metal the layout is home-based and building it writes nothing."""

    def test_local_layout_ignores_host_paths_and_creates_nothing(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        home.mkdir()
        temp_root = tmp_path / "tmp"
        temp_root.mkdir()
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setattr(tempfile, "tempdir", str(temp_root))
        monkeypatch.setattr(
            cfg, "detect_standard_mounts", lambda: {"cache_dir": Path("/cache"), "data_dir": Path("/data")}
        )

        mounts = cfg.get_default_mounts("bare_metal", "myapp")

        assert mounts.config_dir == home / ".config/myapp"
        assert mounts.data_dir == home / ".local/share/myapp"
        assert mounts.logs_dir == home / ".local/share/myapp/logs"
        assert mounts.cache_dir == home / ".cache/myapp"
        assert mounts.temp_dir == temp_root / "myapp"
        assert sorted(p.name for p in home.iterdir()) == []
        assert sorted(p.name for p in temp_root.iterdir()) == []

    def test_mount_config_creates_nothing(self, tmp_path):
        cfg.MountConfig(
            data_dir=tmp_path / "data",
            temp_dir=tmp_path / "tmp",
            logs_dir=tmp_path / "logs",
            cache_dir=tmp_path / "cache",
            run_dir=tmp_path / "run",
        )

        assert sorted(p.name for p in tmp_path.iterdir()) == []
