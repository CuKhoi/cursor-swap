# cursorswap

[English](README.md) | Tiếng Việt

Tool đổi qua lại nhiều account cho **Cursor IDE** (Cursor.app) trên macOS. Lưu nhiều login
Cursor rồi chuyển Cursor.app giữa chúng mà không phải login lại mỗi lần.

> **Phần CLI đã được archive.** Bản trước còn đổi được cả `cursor-agent` CLI (session
> Keychain, API key, `run`/`map`). Code đó nằm ở branch
> [`archive/cli-support`](https://github.com/CuKhoi/cursor-swap/tree/archive/cli-support),
> sẽ làm lại sau; bản này chỉ hỗ trợ IDE.

## Cài đặt / cập nhật

```sh
curl -fsSL https://raw.githubusercontent.com/CuKhoi/cursor-swap/main/install.sh | bash
```

Cùng 1 lệnh để cài, để update, và để thay bản `cursorswap` Bash cũ. Lệnh tự cài
[uv](https://docs.astral.sh/uv/) nếu chưa có, rồi chạy
`uv tool install --force git+https://github.com/CuKhoi/cursor-swap` (chạy tay cũng được).
uv tự lo Python 3.12+; không cần gì thêm. Chỉ chạy trên macOS.

## Bắt đầu nhanh

```sh
# 1. lưu account Cursor.app đang login
cursorswap add work

# 2. đăng xuất IDE CHỈ trên máy này - 'work' vẫn còn hiệu lực
cursorswap logout-local

# 3. login account kia trong Cursor.app, rồi lưu lại
cursorswap add personal

# từ giờ
cursorswap switch personal         # theo tên, số slot, alias hoặc email
cursorswap switch                  # xoay sang account kế tiếp còn enable
cursorswap list                    # các account, account đang active, % usage
```

`switch` và `logout-local` sẽ tắt Cursor.app (hỏi trước - đóng HẾT mọi window IDE), ghi
session, rồi mở lại app. Thêm `-y` hoặc `export CURSOR_SWAP_YES=1` để khỏi bị hỏi.

**Đừng bao giờ dùng "Log out" trong IDE để đổi account.** Nó huỷ session đó trên server
của Cursor, snapshot đã lưu sẽ không dùng được nữa và phải login lại rồi chạy lại `add`.
Dùng `logout-local` (chỉ xoá các dòng auth trên máy này) để thêm account, và `switch` để
đổi account.

## Tất cả lệnh

```
cursorswap add <tên> [--alias A]    lưu account IDE đang login (chạy lại để làm mới)
cursorswap switch [<ref>]           đổi sang <ref>, hoặc xoay sang account kế tiếp
cursorswap logout-local             đăng xuất IDE ở local, không huỷ session
cursorswap list | usage [<ref>]     danh sách + % usage, hoặc % usage của 1 account
cursorswap alias <ref> <tên-tắt>    đặt tên tắt (alias <ref> --unset, hoặc alias để liệt kê)
cursorswap disable|enable <ref>     bỏ ra / đưa vào vòng xoay 'switch'
cursorswap remove <ref>             xoá account đã lưu
cursorswap export|import <file>     backup / khôi phục (token plaintext! import --force để ghi đè)
cursorswap renumber | watch [giây]  đánh lại số slot | lặp 'list' mỗi N giây
cursorswap purge | update | version | lang | help
```

`<ref>` là tên profile, số slot, alias hoặc email. Tên cũ vẫn dùng được: `ide-add`,
`ide-switch`/`ide-use`/`use`, `ide-logout-local`. `--lang vi` (hoặc `CURSOR_SWAP_LANG=vi`)
để hiện toàn bộ bằng tiếng Việt.

## Cách hoạt động

Cursor.app lưu login dạng plaintext - `cursorAuth/accessToken`, `cursorAuth/refreshToken`,
`cursorAuth/cachedEmail`, ... - trong sqlite db local
(`~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`, bảng `ItemTable`) và
chỉ đọc lúc khởi động. `add` chụp các dòng đó vào `~/.cursor-accounts/<tên>/ide-auth.json`;
`switch` tắt app, ghi lại các dòng của account đích trong 1 transaction (xoá các dòng
`cursorAuth/*` của account trước, giữ lại các API key BYOK của bạn), rồi mở lại app.

Tìm ra bằng cách đọc JS đi kèm Cursor.app (`out/vs/workbench/workbench.desktop.main.js`),
không có tài liệu nào:

- **IDE tự refresh token âm thầm** (`POST /oauth/token`, khoảng 1 tuần sau khi token được
  cấp) và token cũ sau đó không dùng được nữa. Vì vậy trước mỗi lần switch, cursorswap lưu
  lại session đang chạy của account cũ vào profile của nó (khớp theo account id trong JWT)
  - bản lưu luôn mới miễn là bạn đổi account bằng cursorswap.
- **"Log out" của IDE gọi `POST /auth/logout`**, huỷ session trên server - nên mới cần
  `logout-local`.

Nếu `list` hiện `session bị từ chối` ở 1 profile, session đã lưu của nó đã bị huỷ: login
lại account đó trong Cursor.app rồi chạy lại `cursorswap add <tên>`.

**% usage** lấy từ chính RPC backend mà Cursor client dùng
(`aiserver.v1.DashboardService/GetCurrentPeriodUsage`), gọi bằng token của profile. Không
document, best-effort: lỗi thì hiện lý do thay cho %. Cả cái này lẫn cấu trúc sqlite đều có
thể đổi ở bất kỳ bản Cursor nào - không cam kết ổn định.

## Dữ liệu & bảo mật

Profile nằm ở `~/.cursor-accounts/<tên>/` (hoặc `CURSOR_SWAP_STORE`): thư mục mode `700`,
file mode `600`, ghi atomic. Token dạng plaintext - cùng mức tin cậy với `state.vscdb` của
chính Cursor.app, vốn cũng lưu token không mã hoá. Hãy giữ store và mọi file `export` như
file password. `import` từ chối link, device và path traversal.

## Phát triển

```sh
git clone https://github.com/CuKhoi/cursor-swap && cd cursor-swap
uv sync
uv run pytest
bash tests/smoke.sh uv run cursorswap
```

Test không bao giờ đụng store thật, Cursor.app thật hay mạng: chúng đặt `CURSOR_SWAP_STORE`
và `CURSOR_SWAP_IDE_DB` sang thư mục tạm và stub `pgrep`/`osascript`/`open`. Chỉ đổi đường
dẫn db **không** ngăn được việc Cursor.app đang chạy bị tắt - phải stub cả `pgrep`.

File Bash `cursorswap` và `cursor-swap` chỉ giữ lại để lệnh `update` của các bản cũ vẫn
chạy; nó chỉ người dùng sang installer ở trên.

## License

MIT - xem [LICENSE](LICENSE).
