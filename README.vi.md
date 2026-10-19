# cursorswap

[English](README.md) | Tiếng Việt

> Đổi tên từ `cursor-swap` (có gạch ngang). Nếu đã cài tên cũ, chạy bất kỳ lệnh
> `cursor-swap` nào 1 lần sẽ tự tải `cursorswap` về rồi forward sang - không đụng gì
> đến account đã lưu. Từ giờ dùng `cursorswap`.

Tool đổi qua lại nhiều account cho [Cursor CLI](https://cursor.com/cli) (`cursor-agent` /
`agent`). Chỉ chạy trên macOS — Linux/Windows dùng cơ chế lưu credential khác, chưa xác minh
được. [Muốn giúp thêm hỗ trợ?](CONTRIBUTING.md) (file tiếng Anh).

Lưu nhiều account Cursor (login thật hoặc API key), đổi qua lại giữa các account, gán 1
thư mục project với 1 account để `cursorswap run` trong thư mục đó luôn dùng đúng account.

## Vì sao cần tool này

`agent login` chỉ hỗ trợ 1 session đang login trên máy — token thật nằm trong macOS
Keychain (`cursor-access-token` / `cursor-refresh-token`, account `cursor-user`), không nằm
trong file config theo từng project. `cursorswap` chụp lại (snapshot) các item Keychain đó
(cộng thêm `authInfo` cache trong `~/.cursor/cli-config.json`) theo từng profile đặt tên, và
phục hồi lại lúc switch.

**Login của Cursor.app là account riêng, tách khỏi CLI** — đổi bên này không đụng bên kia.
cursorswap quản lý cả 2, độc lập nhau: `add`/`login`/`switch`/`run` cho session CLI (dựa
Keychain), `ide-add`/`ide-switch` cho session IDE Cursor.app (dựa sqlite, xem phần dưới).

## Hai loại account

- **session** — login thật qua browser (`agent login`). Swap sang account session sẽ ghi đè
  token Keychain của CLI **toàn cục** — mọi terminal trên máy đang dùng `cursor-agent` thấy
  account mới ngay lập tức. Không có cách nào chạy 2 account session song song ở 2 terminal
  khác nhau; đã test `CURSOR_DATA_DIR` và xác nhận nó **không** cô lập auth theo từng process
  — đây là giới hạn cứng ở tầng OS, không phải tính năng thiếu.
- **api-key** — API key của Cursor (`agent --api-key ...` / `$CURSOR_API_KEY`). Không đụng
  state toàn cục, truyền theo từng lần gọi qua `cursorswap run`. An toàn để chạy song song
  nhiều terminal/project.

## Cài đặt

```sh
curl -fsSL https://raw.githubusercontent.com/CuKhoi/cursor-swap/main/install.sh | bash
```

Cùng 1 lệnh này để cài, để update, và để chuyển từ bản Bash cũ (nó ghi đè
`~/.local/bin/cursorswap`). Lệnh tự cài [uv](https://docs.astral.sh/uv/) nếu chưa có, rồi
chạy `uv tool install --force git+https://github.com/CuKhoi/cursor-swap` (chạy tay cũng
được). uv tự lo Python 3.12+; không có dependency Python lúc chạy, không cần `jq` hay
Bash mới. Cài [`cursor-agent` CLI](https://cursor.com/cli) nếu dùng login/session CLI;
nếu chỉ dùng IDE thì chỉ cần Cursor.app. Chỉ chạy trên macOS.

Profile vẫn nằm ở `~/.cursor-accounts` (hoặc `CURSOR_SWAP_STORE`), không cần chuyển đổi
dữ liệu. Cả hai bản đọc cùng định dạng. `cursorswap update` nay chạy
`uv tool upgrade cursorswap`.

Chạy từ source:

```sh
git clone https://github.com/CuKhoi/cursor-swap
cd cursor-swap
uv sync
uv run pytest
uv run cursorswap --help
```

File Bash `cursorswap` vẫn giữ trong repo để lệnh `update` của các bản cũ tiếp tục chạy
(giờ nó in thêm cách chuyển sang bản Python). `cursor-swap` là shim tương thích; dùng
`cursorswap`.

## Cách dùng

```
# thêm account - login CLI, IDE, hoặc cả 2 trước, rồi:
cursorswap add personal            # chụp cái nào đang login (CLI, IDE, hoặc cả 2)
cursorswap login work              # logout -> login browser -> lưu thành "work" (chỉ CLI)
cursorswap add-token sk-... --email work@co.com --alias work   # API key, không cần login browser

# xem list / status
cursorswap list                    # hiện các account đã lưu, đánh dấu active, hiện % usage
cursorswap status                  # chạy `agent status` + `agent about`
cursorswap usage work              # % usage của 1 account (mặc định: account đang active)

# đổi session CLI toàn cục (và cả session IDE, nếu profile này đã chạy ide-add)
cursorswap switch work             # theo tên, số slot, alias, hoặc email - in % usage sau khi đổi
cursorswap switch                  # xoay vòng sang account kế tiếp (còn enable) - CLI,
                                     # IDE-only, hoặc cả 2; chỉ xài IDE cũng chạy bình thường

# chạy 1 lệnh với account chỉ định, không đụng session toàn cục
# (chỉ thật sự cô lập với profile api-key - xem phần "Hai loại account" ở trên)
cursorswap run work -- create-chat

# gán 1 thư mục project với 1 account, sau đó chỉ cần run
cd ~/code/some-project
cursorswap map work
cursorswap run                     # tự chọn "work" theo mapping thư mục

# account IDE Cursor.app (login riêng, tách khỏi CLI - xem phần "Account IDE" bên dưới)
# 'add' ở trên đã tự chụp IDE nếu đang login rồi - 2 lệnh dưới để chụp lại/đổi riêng IDE.
cursorswap ide-add work            # (chụp lại) CHỈ session IDE đang login hiện tại
cursorswap ide-switch work         # CHỈ đổi session IDE, không đụng CLI
cursorswap ide-logout-local        # đăng xuất IDE ở local, KHÔNG huỷ session trên server

# thêm account IDE thứ 2 (đừng bao giờ dùng Log out của IDE để làm việc này):
cursorswap ide-add personal        # 1. lưu account đang login
cursorswap ide-logout-local        # 2. đăng xuất local - 'personal' vẫn còn hiệu lực
                                   # 3. login account kia trong Cursor.app
cursorswap ide-add work            # 4. lưu nó; giờ 'ide-switch personal|work' đều chạy

# việc vặt khác
cursorswap alias 1 work            # đặt tên tắt cho 1 slot
cursorswap disable work            # tạm loại khỏi vòng xoay switch
cursorswap remove work
cursorswap export backup.tar.gz    # chứa token dạng plaintext - giữ kỹ
cursorswap import backup.tar.gz
cursorswap update                  # uv tool upgrade cursorswap
cursorswap version                 # in ra version đang cài
cursorswap watch                   # lặp lại 'list' mỗi 30s (truyền số để đổi)
cursorswap renumber                # đóng khoảng trống số slot sau khi remove

# ngôn ngữ
cursorswap --lang vi list          # output tiếng Việt cho riêng lần gọi này
export CURSOR_SWAP_LANG=vi          # ...hoặc set 1 lần trong shell rc
```

Chạy `cursorswap --help` để xem đủ danh sách lệnh.

## % Usage (API không document)

`agent status`/`agent about` không expose quota theo account. Nhưng chính JS bundle của CLI
`cursor-agent` có gọi 1 RPC backend — `aiserver.v1.DashboardService/GetCurrentPeriodUsage` —
bằng đúng Bearer access-token mà cursorswap đã lưu sẵn theo từng profile. `list`, `switch`,
và `usage` gọi API này kiểu best-effort, in ra % `total / auto / api` đã dùng.

Đây **không phải API public/có document của Cursor** — tìm ra bằng cách đọc JS minified của
CLI, không phải từ spec chính thức. Không có cam kết ổn định gì cả; Cursor update là có thể
gãy âm thầm. Khi tra thất bại, `list`/`switch` hiện lý do thay cho %, còn `usage` thoát
với mã lỗi. Profile đang active dùng token live. Snapshot không active có thể bị từ chối
trước cả hạn JWT; switch không sửa được token đã bị thu hồi. Khi đó cần login lại rồi
chạy `add` / `ide-add`.

## Account IDE (định dạng lưu không document)

Cursor.app (bản desktop editor) là **login tách riêng khỏi CLI** — có thể đang login account
hoàn toàn khác. Session của nó không nằm trong Keychain chút nào; nó là 2 dòng plaintext —
`cursorAuth/accessToken` / `cursorAuth/refreshToken` — trong sqlite db local của chính app
(`~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`, table `ItemTable`).
Tìm ra bằng cách đọc file đó (lúc app đã tắt hẳn, để WAL journal được checkpoint) — không
phải item Keychain `Cursor Safe Storage`, cái đó là key mã hoá riêng của Electron cho mấy thứ
khác, không liên quan gì đến login của IDE.

- `cursorswap ide-add <name>` chụp lại session IDE đang login (chạy được dù Cursor.app đang
  mở hay đã tắt).
- `cursorswap ide-switch <ref>` **chỉ** phục hồi session IDE, không đụng CLI.
- Sau khi 1 profile đã có session IDE được chụp, `cursorswap switch <ref>` bình thường sẽ đổi
  **cả 2** — CLI trước, IDE sau — trong 1 lệnh. Profile nào chưa từng chạy `ide-add` thì
  `switch` vẫn y như cũ (chỉ CLI, không hỏi gì về IDE).

Dù chạy qua đường nào, đổi session IDE cũng cần app **tắt hẳn** trước — nó chỉ đọc auth từ
disk lúc khởi động, và process đang sống có thể ghi đè lại thứ mình vừa ghi. cursorswap tự
tắt app cho bạn (hỏi xác nhận trước — việc này đóng hết mọi window IDE đang mở) rồi mở lại
sau khi xong. Thêm `-y`/`--yes` để bỏ qua hỏi xác nhận, hoặc `export CURSOR_SWAP_YES=1`
trong shell rc để bỏ qua luôn mọi lần (không chỉ riêng chỗ này).

**Đừng dùng “Log out” trong IDE để đổi account** — lệnh đó thu hồi session trên server,
khiến snapshot đã lưu không dùng được. Dùng `ide-switch`: tool lưu lại token live của
account cũ trước khi phục hồi account mới, để giữ token đã được Cursor tự xoay.
Khi phục hồi, tool xoá cache `cursorAuth/*` cũ trong cùng transaction, giữ lại các key BYOK.
Muốn login account mới thì đăng xuất bằng `cursorswap ide-logout-local` — lệnh chỉ xoá các
dòng auth trên máy này, nên session cũ không bao giờ bị huỷ (chỉ có ở bản Python).

Cùng lưu ý như % usage: **định dạng lưu trên disk không document**, tìm ra bằng cách soi file,
không phải từ spec chính thức. Cursor update là có thể đổi; nếu `ide-add`/`ide-switch` tự
nhiên lỗi thì nhiều khả năng do đây — không có cam kết ổn định.

## Cái này KHÔNG làm được

- **Không auto-switch.** % usage ở trên đến từ API không document, có thể đổi bất cứ lúc nào
  không báo trước — không đáng để xây tự động hóa không giám sát trên đó. Tự chạy
  `cursorswap watch` hoặc `usage` rồi switch tay.
- **TUI / menubar: chưa triển khai.** Nay khả thi với package Python nhưng chưa có
  trong bản này. `watch` đã cung cấp vòng lặp poll trong terminal.
- **Không chạy song song thật sự nhiều session-account.** Đã test `CURSOR_DATA_DIR` xác nhận
  nó không cô lập auth theo process. Cần chạy song song thật thì dùng `add-token` + `run`
  thay vì account session.

## Ngôn ngữ

`--lang <en|vi>` (hoặc `CURSOR_SWAP_LANG=vi`) đổi toàn bộ output của cursorswap — `list`,
`switch`, lỗi, `--help`, mọi thứ — sang tiếng Việt. Tên lệnh và cú pháp không bao giờ dịch
(`cursorswap switch` luôn là `cursorswap switch`), chỉ mô tả/message xung quanh mới dịch.
Chỗ nào chưa dịch thì fallback về tiếng Anh, không bao giờ ra dòng trống.

## Màu sắc

`list`/`switch`/`usage` dùng bảng màu tối giản (1 accent màu ấm, text phụ màu xám nhạt,
xanh/vàng/đỏ cho % usage theo mức độ) — tự tắt khi output không phải terminal (bị pipe/redirect),
tôn trọng [`NO_COLOR`](https://no-color.org/) / `FORCE_COLOR`.

## Dữ liệu & bảo mật

Profile được lưu ở `~/.cursor-accounts/<tên>/` (dir mode `700`, file token/key mode `600`) —
plaintext trên disk, cùng mức tin cậy như file `~/.cursor/cli-config.json` của chính
`cursor-agent`, và như output của `security find-generic-password`. File `ide-auth.json` (từ
`ide-add`) cũng plaintext, cùng mức tin cậy như `state.vscdb` của chính Cursor.app — vốn dĩ đã
lưu token đó không mã hoá sẵn rồi. Ai đọc được account máy bạn thì cũng đọc được mấy thứ này
rồi, tool này không hạ thấp mức bảo mật đó — nhưng hãy coi store (và file `export` bất kỳ) như
1 file password thật sự.

Python ghi file qua file tạm mode `600` rồi đổi tên atomic; thư mục mode `700`.
Import nhận archive của Bash, bỏ qua profile đã có trừ khi dùng `--force`, và không nhập
`mappings.json` (giống Bash). Link/device và đường dẫn thoát khỏi archive bị từ chối.
Tên profile phải là tên thư mục đơn, không bắt đầu bằng dấu chấm.

Khi test, đặt cả `CURSOR_SWAP_STORE` và `CURSOR_SWAP_IDE_DB` vào thư mục tạm, đồng thời
mock `security`, `pgrep`, `osascript`, `open`, `agent`. Chỉ đổi DB không ngăn việc tắt app
thật. `uv run pytest` và `bash tests/smoke.sh uv run cursorswap` đã cô lập các phần này.

## License

MIT — xem [LICENSE](LICENSE).
