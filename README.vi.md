# cursor-swap

[English](README.md) | Tiếng Việt

Tool đổi qua lại nhiều account cho [Cursor CLI](https://cursor.com/cli) (`cursor-agent` /
`agent`). Chỉ chạy trên macOS — Linux/Windows dùng cơ chế lưu credential khác, chưa xác minh
được. [Muốn giúp thêm hỗ trợ?](CONTRIBUTING.md) (file tiếng Anh).

Lưu nhiều account Cursor (login thật hoặc API key), đổi qua lại giữa các account, gán 1
thư mục project với 1 account để `cursor-swap run` trong thư mục đó luôn dùng đúng account.

## Vì sao cần tool này

`agent login` chỉ hỗ trợ 1 session đang login trên máy — token thật nằm trong macOS
Keychain (`cursor-access-token` / `cursor-refresh-token`, account `cursor-user`), không nằm
trong file config theo từng project. `cursor-swap` chụp lại (snapshot) các item Keychain đó
(cộng thêm `authInfo` cache trong `~/.cursor/cli-config.json`) theo từng profile đặt tên, và
phục hồi lại lúc switch.

**Login của Cursor.app là account riêng, tách khỏi CLI** — đổi bên này không đụng bên kia.
cursor-swap quản lý cả 2, độc lập nhau: `add`/`login`/`switch`/`run` cho session CLI (dựa
Keychain), `ide-add`/`ide-switch` cho session IDE Cursor.app (dựa sqlite, xem phần dưới).

## Hai loại account

- **session** — login thật qua browser (`agent login`). Swap sang account session sẽ ghi đè
  token Keychain của CLI **toàn cục** — mọi terminal trên máy đang dùng `cursor-agent` thấy
  account mới ngay lập tức. Không có cách nào chạy 2 account session song song ở 2 terminal
  khác nhau; đã test `CURSOR_DATA_DIR` và xác nhận nó **không** cô lập auth theo từng process
  — đây là giới hạn cứng ở tầng OS, không phải tính năng thiếu.
- **api-key** — API key của Cursor (`agent --api-key ...` / `$CURSOR_API_KEY`). Không đụng
  state toàn cục, truyền theo từng lần gọi qua `cursor-swap run`. An toàn để chạy song song
  nhiều terminal/project.

## Cài đặt

```
curl -fsSL https://raw.githubusercontent.com/CuKhoi/cursor-switch/main/install.sh | bash
```

Cài vào `~/.local/bin/cursor-swap`. Muốn cài chỗ khác thì truyền thêm arg:
`curl -fsSL .../install.sh | bash -s -- /usr/local/bin`.

Hoặc clone về chạy local:

```
git clone git@github.com:CuKhoi/cursor-switch.git
cd cursor-switch
./install.sh
```

Cần có sẵn `jq` (`brew install jq`) và [`cursor-agent` CLI](https://cursor.com/cli).

## Cách dùng

```
# thêm account - login CLI, IDE, hoặc cả 2 trước, rồi:
cursor-swap add personal            # chụp cái nào đang login (CLI, IDE, hoặc cả 2)
cursor-swap login work              # logout -> login browser -> lưu thành "work" (chỉ CLI)
cursor-swap add-token sk-... --email work@co.com --alias work   # API key, không cần login browser

# xem list / status
cursor-swap list                    # hiện các account đã lưu, đánh dấu active, hiện % usage
cursor-swap status                  # chạy `agent status` + `agent about`
cursor-swap usage work              # % usage của 1 account (mặc định: account đang active)

# đổi session CLI toàn cục (và cả session IDE, nếu profile này đã chạy ide-add)
cursor-swap switch work             # theo tên, số slot, alias, hoặc email - in % usage sau khi đổi
cursor-swap switch                  # xoay vòng sang account kế tiếp (còn enable) - CLI,
                                     # IDE-only, hoặc cả 2; chỉ xài IDE cũng chạy bình thường

# chạy 1 lệnh với account chỉ định, không đụng session toàn cục
# (chỉ thật sự cô lập với profile api-key - xem phần "Hai loại account" ở trên)
cursor-swap run work -- create-chat

# gán 1 thư mục project với 1 account, sau đó chỉ cần run
cd ~/code/some-project
cursor-swap map work
cursor-swap run                     # tự chọn "work" theo mapping thư mục

# account IDE Cursor.app (login riêng, tách khỏi CLI - xem phần "Account IDE" bên dưới)
# 'add' ở trên đã tự chụp IDE nếu đang login rồi - 2 lệnh dưới để chụp lại/đổi riêng IDE.
cursor-swap ide-add work            # (chụp lại) CHỈ session IDE đang login hiện tại
cursor-swap ide-switch work         # CHỈ đổi session IDE, không đụng CLI

# việc vặt khác
cursor-swap alias 1 work            # đặt tên tắt cho 1 slot
cursor-swap disable work            # tạm loại khỏi vòng xoay switch
cursor-swap remove work
cursor-swap export backup.tar.gz    # chứa token dạng plaintext - giữ kỹ
cursor-swap import backup.tar.gz
cursor-swap update                  # tải bản mới nhất từ GitHub, ghi đè chính nó
cursor-swap version                 # in ra version đang cài
cursor-swap watch                   # lặp lại 'list' mỗi 30s (truyền số để đổi)
cursor-swap renumber                # đóng khoảng trống số slot sau khi remove

# ngôn ngữ
cursor-swap --lang vi list          # output tiếng Việt cho riêng lần gọi này
export CURSOR_SWAP_LANG=vi          # ...hoặc set 1 lần trong shell rc
```

Chạy `cursor-swap --help` để xem đủ danh sách lệnh.

## % Usage (API không document)

`agent status`/`agent about` không expose quota theo account. Nhưng chính JS bundle của CLI
`cursor-agent` có gọi 1 RPC backend — `aiserver.v1.DashboardService/GetCurrentPeriodUsage` —
bằng đúng Bearer access-token mà cursor-swap đã lưu sẵn theo từng profile. `list`, `switch`,
và `usage` gọi API này kiểu best-effort, in ra % `total / auto / api` đã dùng.

Đây **không phải API public/có document của Cursor** — tìm ra bằng cách đọc JS minified của
CLI, không phải từ spec chính thức. Không có cam kết ổn định gì cả; Cursor update là có thể
gãy âm thầm, lúc đó mấy lệnh này chỉ đơn giản không hiện gì (không bao giờ crash vì lý do
này). % usage của 1 profile đã lưu nhưng đang không active phụ thuộc vào access-token đã chụp
của profile đó còn hạn hay không — nếu hết hạn, `switch` sang account đó 1 lần để refresh lại.

## Account IDE (định dạng lưu không document)

Cursor.app (bản desktop editor) là **login tách riêng khỏi CLI** — có thể đang login account
hoàn toàn khác. Session của nó không nằm trong Keychain chút nào; nó là 2 dòng plaintext —
`cursorAuth/accessToken` / `cursorAuth/refreshToken` — trong sqlite db local của chính app
(`~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`, table `ItemTable`).
Tìm ra bằng cách đọc file đó (lúc app đã tắt hẳn, để WAL journal được checkpoint) — không
phải item Keychain `Cursor Safe Storage`, cái đó là key mã hoá riêng của Electron cho mấy thứ
khác, không liên quan gì đến login của IDE.

- `cursor-swap ide-add <name>` chụp lại session IDE đang login (chạy được dù Cursor.app đang
  mở hay đã tắt).
- `cursor-swap ide-switch <ref>` **chỉ** phục hồi session IDE, không đụng CLI.
- Sau khi 1 profile đã có session IDE được chụp, `cursor-swap switch <ref>` bình thường sẽ đổi
  **cả 2** — CLI trước, IDE sau — trong 1 lệnh. Profile nào chưa từng chạy `ide-add` thì
  `switch` vẫn y như cũ (chỉ CLI, không hỏi gì về IDE).

Dù chạy qua đường nào, đổi session IDE cũng cần app **tắt hẳn** trước — nó chỉ đọc auth từ
disk lúc khởi động, và process đang sống có thể ghi đè lại thứ mình vừa ghi. cursor-swap tự
tắt app cho bạn (hỏi xác nhận trước — việc này đóng hết mọi window IDE đang mở) rồi mở lại
sau khi xong. Thêm `-y`/`--yes` để bỏ qua hỏi xác nhận, hoặc `export CURSOR_SWAP_YES=1`
trong shell rc để bỏ qua luôn mọi lần (không chỉ riêng chỗ này).

Cùng lưu ý như % usage: **định dạng lưu trên disk không document**, tìm ra bằng cách soi file,
không phải từ spec chính thức. Cursor update là có thể đổi; nếu `ide-add`/`ide-switch` tự
nhiên lỗi thì nhiều khả năng do đây — không có cam kết ổn định.

## Cái này KHÔNG làm được

- **Không auto-switch.** % usage ở trên đến từ API không document, có thể đổi bất cứ lúc nào
  không báo trước — không đáng để xây tự động hóa không giám sát trên đó. Tự chạy
  `cursor-swap watch` hoặc `usage` rồi switch tay.
- **Không tui / menubar.** Sai mô hình phân phối cho 1 file bash tự update — giao diện
  full-screen cần runtime khác (Python+Textual) và cách cài khác, app menu-bar cần build
  Swift/rumps riêng, ký code, notarize riêng. Sẽ là dự án khác, không phải tính năng của
  file này. (`watch` — vòng lặp poll trong terminal thuần — hợp với bash nên đã làm.)
- **Không chạy song song thật sự nhiều session-account.** Đã test `CURSOR_DATA_DIR` xác nhận
  nó không cô lập auth theo process. Cần chạy song song thật thì dùng `add-token` + `run`
  thay vì account session.

## Ngôn ngữ

`--lang <en|vi>` (hoặc `CURSOR_SWAP_LANG=vi`) đổi toàn bộ output của cursor-swap — `list`,
`switch`, lỗi, `--help`, mọi thứ — sang tiếng Việt. Tên lệnh và cú pháp không bao giờ dịch
(`cursor-swap switch` luôn là `cursor-swap switch`), chỉ mô tả/message xung quanh mới dịch.
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

## License

MIT — xem [LICENSE](LICENSE).
