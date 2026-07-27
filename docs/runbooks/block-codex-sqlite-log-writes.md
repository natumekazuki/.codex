# `logs_2.sqlite`への新規ログ挿入を止める

## 目的

Codexが`%USERPROFILE%\.codex\logs_2.sqlite`へ診断ログを書き続けることで、SSDへの書き込み量が増える問題を暫定的に抑える。

この対策は`logs`テーブルへの`INSERT`をSQLiteトリガーで無視する。既存のログは削除せず、会話やスレッドの状態を保存する別のSQLiteデータベースには影響しない。

このrunbookは端末間で共有する手順だけを扱う。適用状態は端末ごとに「確認」の手順で判定し、このファイルには記録しない。

## 動作

この手順が作成するトリガーは次のとおり。

```sql
CREATE TRIGGER block_log_inserts
BEFORE INSERT ON logs
BEGIN
    SELECT RAISE(IGNORE);
END;
```

`RAISE(IGNORE)`を使うため、挿入元へSQLiteエラーを返さず、対象のログ行だけを破棄する。

## 確認

PowerShellから次を実行する。

```powershell
@'
import os
import sqlite3
from pathlib import Path

path = Path(os.environ["USERPROFILE"]) / ".codex" / "logs_2.sqlite"
expected = " ".join(
    """
    CREATE TRIGGER block_log_inserts
    BEFORE INSERT ON logs
    BEGIN
        SELECT RAISE(IGNORE);
    END
    """.upper().split()
)
connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
try:
    quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
    trigger = connection.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'trigger' AND name = 'block_log_inserts'
        """
    ).fetchone()
    if trigger is None:
        print("NOT INSTALLED")
    else:
        actual = " ".join(trigger[0].upper().split()).rstrip(";")
        status = "INSTALLED" if actual == expected else "UNEXPECTED DEFINITION"
        print(status)
        print(f"quick_check={quick_check}")
        print(trigger[0])
finally:
    connection.close()
'@ | python -
```

`INSTALLED`、`quick_check=ok`、トリガーのSQLが表示されれば、この対策は有効になっている。`UNEXPECTED DEFINITION`の場合は、同名で異なるトリガーが存在するため、その内容を確認してから修正する。

## 適用または再適用

データベースの再作成やmigrationでトリガーが失われた場合は、PowerShellから次を実行する。

```powershell
@'
import os
import sqlite3
from pathlib import Path

path = Path(os.environ["USERPROFILE"]) / ".codex" / "logs_2.sqlite"
expected = " ".join(
    """
    CREATE TRIGGER block_log_inserts
    BEFORE INSERT ON logs
    BEGIN
        SELECT RAISE(IGNORE);
    END
    """.upper().split()
)
connection = sqlite3.connect(f"{path.as_uri()}?mode=rw", uri=True, timeout=60)
connection.execute("PRAGMA busy_timeout = 60000")
try:
    connection.execute("BEGIN IMMEDIATE")
    if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise RuntimeError("quick_check failed before trigger installation")
    existing = connection.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'trigger' AND name = 'block_log_inserts'
        """
    ).fetchone()
    if existing is None:
        connection.execute(
            """
            CREATE TRIGGER block_log_inserts
            BEFORE INSERT ON logs
            BEGIN
                SELECT RAISE(IGNORE);
            END
            """
        )
    else:
        actual = " ".join(existing[0].upper().split()).rstrip(";")
        if actual != expected:
            raise RuntimeError("block_log_inserts has an unexpected definition")
    if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise RuntimeError("quick_check failed after trigger installation")
    connection.commit()
finally:
    if connection.in_transaction:
        connection.rollback()
    connection.close()
'@ | python -
```

適用後は「確認」の手順を実行する。

## 解除

Codex側で問題が修正され、ログ保存を再開する場合は、PowerShellから次を実行する。

```powershell
@'
import os
import sqlite3
from pathlib import Path

path = Path(os.environ["USERPROFILE"]) / ".codex" / "logs_2.sqlite"
expected = " ".join(
    """
    CREATE TRIGGER block_log_inserts
    BEFORE INSERT ON logs
    BEGIN
        SELECT RAISE(IGNORE);
    END
    """.upper().split()
)
connection = sqlite3.connect(f"{path.as_uri()}?mode=rw", uri=True, timeout=60)
connection.execute("PRAGMA busy_timeout = 60000")
try:
    connection.execute("BEGIN IMMEDIATE")
    if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise RuntimeError("quick_check failed before trigger removal")
    existing = connection.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'trigger' AND name = 'block_log_inserts'
        """
    ).fetchone()
    if existing is not None:
        actual = " ".join(existing[0].upper().split()).rstrip(";")
        if actual != expected:
            raise RuntimeError("block_log_inserts has an unexpected definition")
        connection.execute("DROP TRIGGER block_log_inserts")
    if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise RuntimeError("quick_check failed after trigger removal")
    connection.commit()
finally:
    if connection.in_transaction:
        connection.rollback()
    connection.close()
'@ | python -
```

## 制約と再確認の条件

- この対策が止めるのは`logs`テーブルへの新規挿入であり、データベースファイルをOSレベルで読み取り専用にはしない。
- Codexはログ挿入とは別に、保持期限を過ぎた行の削除やWAL checkpointを起動時に実行する。そのため、継続的な`INSERT`は止まるが、ファイルへの書き込みが将来も完全にゼロになることまでは保証しない。
- 既存の`logs_2.sqlite`のファイルサイズは縮小しない。縮小には別途、削除または`VACUUM`などの操作が必要になる。
- Codexの更新、データベースの再作成、schema migration後は、トリガーが残っているか確認する。
- `logs_2.sqlite`またはWALの継続的な増加が再発した場合は、トリガーの存在と対象データベースの場所を確認する。
- 診断ログが保存されなくなるため、Codexの不具合調査でログ提出が必要な期間は一時的に解除する。

## 参考

- [Persistent trace logs written to SQLite](https://github.com/openai/codex/issues/17320)
- [High SQLite insert and prune rate after mitigations](https://github.com/openai/codex/issues/29532)
- [SQLite logging mitigation tracking](https://github.com/openai/codex/issues/28224)
- [Codex SQLite log insertion and maintenance implementation](https://github.com/openai/codex/blob/main/codex-rs/state/src/runtime/logs.rs)
