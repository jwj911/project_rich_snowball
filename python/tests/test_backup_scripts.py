"""备份/恢复脚本单元测试。

覆盖 ``scripts._pg_utils`` 的连接串解析与参数合并逻辑。
外部 pg 工具调用依赖 PostgreSQL 客户端环境，不在 CI 中强制执行。
"""

import os
import sys
from argparse import Namespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts._pg_utils import merge_connection_params, parse_database_url


class TestParseDatabaseUrl:
    def test_parse_full_url(self):
        url = "postgresql://futures:futures123@localhost:15432/futures_community"
        params = parse_database_url(url)
        assert params == {
            "host": "localhost",
            "port": "15432",
            "user": "futures",
            "password": "futures123",
            "dbname": "futures_community",
        }

    def test_parse_minimal_url(self):
        url = "postgresql://localhost/mydb"
        params = parse_database_url(url)
        assert params == {"host": "localhost", "dbname": "mydb"}

    def test_parse_empty_url(self):
        assert parse_database_url(None) == {}
        assert parse_database_url("") == {}

    def test_parse_unsupported_scheme(self):
        try:
            parse_database_url("mysql://localhost/db")
        except ValueError as exc:
            assert "Unsupported database URL scheme" in str(exc)
        else:
            raise AssertionError("Expected ValueError for unsupported scheme")


class TestMergeConnectionParams:
    def test_args_override_env_and_url(self):
        args = Namespace(
            host="arg-host",
            port="1234",
            user="arg-user",
            password="arg-pass",
            dbname="arg-db",
        )
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://url-user:url-pass@url-host:5432/url-db",
                "PGHOST": "env-host",
                "PGUSER": "env-user",
            },
            clear=False,
        ):
            params = merge_connection_params(args)

        assert params["host"] == "arg-host"
        assert params["port"] == "1234"
        assert params["user"] == "arg-user"
        assert params["password"] == "arg-pass"
        assert params["dbname"] == "arg-db"

    def test_env_overrides_url(self):
        args = Namespace(host=None, port=None, user=None, password=None, dbname=None)
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://url-user:url-pass@url-host:5432/url-db",
                "PGHOST": "env-host",
                "PGPORT": "15432",
                "PGDATABASE": "env-db",
            },
            clear=False,
        ):
            params = merge_connection_params(args)

        assert params["host"] == "env-host"
        assert params["port"] == "15432"
        assert params["user"] == "url-user"
        assert params["password"] == "url-pass"
        assert params["dbname"] == "env-db"

    def test_no_url_no_env(self):
        args = Namespace(host=None, port=None, user=None, password=None, dbname=None)
        with patch.dict(os.environ, {}, clear=True):
            params = merge_connection_params(args)
        assert params == {}
