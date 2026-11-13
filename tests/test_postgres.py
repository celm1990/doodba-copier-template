import uuid
from pathlib import Path

import pytest
from copier import run_copy
from python_on_whales import DockerClient

from .conftest import DBVER_PER_ODOO, TRAEFIK_VERSION


@pytest.mark.parametrize("dbver", ("oldest", "latest"))
def test_postgresql_client_versions(
    cloned_template: Path,
    supported_odoo_version: float,
    single_project_path: Path,
    dbver: str,
):
    """Test multiple postgresql-client versions in odoo, db and duplicity services"""
    dbver_raw = DBVER_PER_ODOO[supported_odoo_version][dbver]
    dbver_major = dbver_raw.split(".")[0]
    docker = DockerClient(compose_files=["prod.yaml"])
    dbver_major = dbver_raw.split(".")[0]
    docker = DockerClient(compose_files=["prod.yaml"])
    run_copy(
        str(cloned_template),
        str(single_project_path),
        data={
            "odoo_version": supported_odoo_version,
            "project_name": uuid.uuid4().hex,
            "odoo_proxy": "",
            "postgres_version": dbver_raw,
            "backup_dst": "/tmp/dummy",
        },
        vcs_ref="HEAD",
        defaults=True,
        overwrite=True,
        unsafe=True,
    )
    docker.compose.down(remove_orphans=True, volumes=True)
    docker.compose.build()
    odoo_pgdump_stdout = docker.compose.run(
        "odoo",
        command=["pg_dump", "--version"],
        remove=True,
        tty=False,
    )
    odoo_pgdump_mver = (
        odoo_pgdump_stdout.splitlines()[-1].strip().split(" ")[2].split(".")[0]
    )
    db_pgdump_stdout = docker.compose.run(
        "db",
        command=["pg_dump", "--version"],
        remove=True,
        tty=False,
    )
    db_pgdump_mver = (
        db_pgdump_stdout.splitlines()[-1].strip().split(" ")[2].split(".")[0]
    )
    backup_pgdump_stdout = docker.compose.run(
        "backup",
        command=["pg_dump", "--version"],
        remove=True,
        tty=False,
    )
    backup_pgdump_mver = (
        backup_pgdump_stdout.splitlines()[-1].strip().split(" ")[2].split(".")[0]
    )
    assert odoo_pgdump_mver == db_pgdump_mver == backup_pgdump_mver == dbver_major


def test_postgresql_exposed(
    cloned_template: Path,
    supported_odoo_version: float,
    single_project_path: Path,
):
    """Render PostgreSQL exposure for password and certificate authentication."""
    if TRAEFIK_VERSION != "3":
        pytest.skip("Exposing postgres only supported on traefik v3")
    project_name = "dct-testing-odoo"
    run_copy(
        str(cloned_template),
        str(single_project_path),
        data={
            "odoo_version": supported_odoo_version,
            "postgres_exposed": True,
            "postgres_exposed_authentication": "password",
            "project_name": "dct-testing-odoo",
            "traefik_version": 3,
        },
        vcs_ref="HEAD",
        defaults=True,
        overwrite=True,
        unsafe=True,
    )
    test_config = DockerClient(compose_files=["prod.yaml"]).compose.config()
    db_container = test_config.services["db"]
    # Custom: postgres_exposed_databases defaults to [postgres_dbname] (project_name)
    assert db_container.environment["WAN_DATABASES"] == f'["{project_name}"]'
    assert db_container.environment["WAN_USERS"] == '["readonly_user"]'
    assert db_container.environment["WAN_AUTH_METHOD"] == "scram-sha-256"
    traefik_router = f"traefik.tcp.routers.{project_name}-{str(supported_odoo_version).replace('.', '-')}-prod-database"  # noqa: E501
    assert db_container.labels[traefik_router + ".rule"] == "HostSNI(`*`)"
    assert traefik_router + ".tls" not in db_container.labels
    assert traefik_router + ".tls.passthrough" not in db_container.labels
    assert traefik_router + ".tls.certResolver" not in db_container.labels

    run_copy(
        str(cloned_template),
        str(single_project_path),
        data={
            "odoo_version": supported_odoo_version,
            "postgres_exposed": True,
            "postgres_exposed_authentication": "certificate",
            "project_name": "dct-testing-odoo",
            "traefik_version": 3,
        },
        vcs_ref="HEAD",
        defaults=True,
        overwrite=True,
        unsafe=True,
    )
    test_config = DockerClient(compose_files=["prod.yaml"]).compose.config()
    db_container = test_config.services["db"]
    assert "WAN_AUTH_METHOD" not in db_container.environment
    assert db_container.labels[traefik_router + ".tls.passthrough"] == "true"
