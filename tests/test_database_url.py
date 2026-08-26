from app.database.pool import pool_connect_args


def test_local_url_does_not_enable_ssl():
    args = pool_connect_args("postgresql://postgres@localhost:5432/crimax_sports")
    assert "ssl" not in args
    assert args["dsn"].startswith("postgresql://")
    assert args["min_size"] == 1


def test_sqlalchemy_prefix_and_libpq_params_are_stripped():
    args = pool_connect_args(
        "postgresql+asyncpg://user:pass@ep-example.neon.tech/db"
        "?sslmode=require&channel_binding=require"
    )
    assert "+asyncpg" not in args["dsn"]
    assert "sslmode" not in args["dsn"]
    assert "channel_binding" not in args["dsn"]
    assert args["ssl"] is not None


def test_remote_url_enables_ssl_by_default():
    args = pool_connect_args("postgresql://user:pass@db.example.com:5432/crimax")
    assert args["ssl"] is not None
