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

**Khác với account của Cursor IDE.** Các item Keychain nói trên chỉ thuộc về CLI — Cursor.app
(bản desktop editor) dùng 1 item riêng (`Cursor Safe Storage`) để mã hoá local storage của
nó, nên đổi account CLI không đụng vào session IDE đang chạy. (Đã kiểm chứng bằng cách đọc
metadata của Keychain item, tool này không đụng/đọc item đó.)

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
# thêm account
cursor-swap login work              # logout -> login browser -> lưu thành "work"
cursor-swap add personal            # chụp lại account đang login hiện tại, lưu thành "personal"
cursor-swap add-token sk-... --email work@co.com --alias work   # API key, không cần login browser

# xem list / status
cursor-swap list                    # hiện các account đã lưu, đánh dấu active, hiện % usage
cursor-swap status                  # chạy `agent status` + `agent about`
cursor-swap usage work              # % usage của 1 account (mặc định: account đang active)

# đổi session CLI (toàn cục)
cursor-swap switch work             # theo tên, số slot, alias, hoặc email - in % usage sau khi đổi
cursor-swap switch                  # xoay vòng sang account session kế tiếp (còn enable)

# chạy 1 lệnh với account chỉ định, không đụng session toàn cục
# (chỉ thật sự cô lập với profile api-key - xem phần "Hai loại account" ở trên)
cursor-swap run work -- create-chat

# gán 1 thư mục project với 1 account, sau đó chỉ cần run
cd ~/code/some-project
cursor-swap map work
cursor-swap run                     # tự chọn "work" theo mapping thư mục

# việc vặt khác
cursor-swap alias 1 work            # đặt tên tắt cho 1 slot
cursor-swap disable work            # tạm loại khỏi vòng xoay switch
cursor-swap remove work
cursor-swap export backup.tar.gz    # chứa token dạng plaintext - giữ kỹ
cursor-swap import backup.tar.gz
cursor-swap update                  # tải bản mới nhất từ GitHub, ghi đè chính nó
cursor-swap version                 # in ra version đang cài
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

## Cái này KHÔNG làm được

- **Không auto-switch / tui / watch / menubar.** % usage ở trên đến từ API không document,
  có thể đổi bất cứ lúc nào không báo trước — không đáng để xây tự động hóa không giám sát
  trên đó. Tự chạy `cursor-swap usage` rồi switch tay.
- **Không chạy song song thật sự nhiều session-account.** Đã test `CURSOR_DATA_DIR` xác nhận
  nó không cô lập auth theo process. Cần chạy song song thật thì dùng `add-token` + `run`
  thay vì account session.

## Dữ liệu & bảo mật

Profile được lưu ở `~/.cursor-accounts/<tên>/` (dir mode `700`, file token/key mode `600`) —
plaintext trên disk, cùng mức tin cậy như file `~/.cursor/cli-config.json` của chính
`cursor-agent`, và như output của `security find-generic-password`. Ai đọc được account máy
bạn thì cũng đọc được Keychain item đang sống rồi, tool này không hạ thấp mức bảo mật đó — nhưng
hãy coi store (và file `export` bất kỳ) như 1 file password thật sự.

## License

MIT — xem [LICENSE](LICENSE).
