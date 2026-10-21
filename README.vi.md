# cursorswap

[English](README.md) | Tiếng Việt

Đổi **Cursor IDE** (Cursor.app) qua lại giữa nhiều account mà không phải login lại.
Chạy trên macOS và Windows (bản Windows mới làm, chưa test trên máy thật - gặp lỗi
thì báo lại).

## Cài / cập nhật

```sh
curl -fsSL https://raw.githubusercontent.com/CuKhoi/cursor-swap/main/install.sh | bash
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/CuKhoi/cursor-swap/main/install.ps1 | iex"
```

Chạy lại đúng lệnh này để cập nhật. cursorswap cũng tự báo khi có bản mới.

## Thêm account

```sh
cursorswap add acc1          # 1. lưu account Cursor đang login
cursorswap logout-local      # 2. đăng xuất Cursor (acc1 vẫn được giữ)
                             # 3. login account tiếp theo trong Cursor, đợi vài giây
cursorswap add acc2          # 4. lưu lại
```

Lặp lại bước 2–4 cho các account khác.

## Sử dụng

```sh
cursorswap switch            # chuyển sang account kế tiếp
cursorswap switch acc2       # chuyển sang account cụ thể
cursorswap list              # xem các account + % usage
```

Khi switch, Cursor tự tắt rồi mở lại.

## Quy tắc

- **Không bao giờ bấm "Log out" trong Cursor.** Nó làm hỏng session đã lưu của account
  đó. Dùng `cursorswap logout-local` thay thế.
- Nếu `list` báo `session bị từ chối` ở account nào: login lại account đó trong Cursor rồi
  chạy `cursorswap add <tên>`.
- Đợi agent/chat đang chạy xong rồi hãy switch - Cursor sẽ bị tắt trong lúc switch.

## Switch giữ lại những gì

Chỉ có login thay đổi. Những thứ sau giữ nguyên:

- lịch sử chat, composer, agent
- các window, project, tab đang mở
- file chưa lưu (nếu Cursor hỏi lưu file thì switch bị huỷ, không có gì thay đổi)
- API key riêng của bạn (OpenAI, Claude, ...) cài trong Cursor

## Lệnh khác

| Lệnh | Tác dụng |
|---|---|
| `cursorswap alias acc2 b` | đặt tên ngắn: `cursorswap switch b` |
| `cursorswap disable acc2` / `enable` | bỏ ra / đưa vào vòng `switch` |
| `cursorswap remove acc2` | xoá account đã lưu |
| `cursorswap export backup.tar.gz` / `import` | backup / khôi phục (chứa token - giữ kín) |
| `cursorswap --lang vi list` | hiện tiếng Việt |
| `cursorswap help` | xem tất cả lệnh |

## Cần biết

- Account được lưu ở `~/.cursor-accounts` (chỉ user của bạn đọc được).
- Windows: nên để Cursor mở 1 cửa sổ khi switch. Mở nhiều cửa sổ thì sau khi switch có
  thể chỉ cửa sổ cuối được mở lại.
- Cursor không công bố cách lưu login, nên 1 bản cập nhật Cursor có thể làm tool này hỏng.
- Hỗ trợ `cursor-agent` CLI đang tạm dừng; code cũ nằm ở branch
  [`archive/cli-support`](https://github.com/CuKhoi/cursor-swap/tree/archive/cli-support).
- Dành cho dev: xem [CONTRIBUTING.md](CONTRIBUTING.md) và [CLAUDE.md](CLAUDE.md).

## License

MIT - xem [LICENSE](LICENSE).
