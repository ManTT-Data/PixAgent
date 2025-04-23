# API Documentation for PostgreSQL Endpoints

## Tổng quan

API PostgreSQL cung cấp các điểm cuối để quản lý dữ liệu từ cơ sở dữ liệu PostgreSQL, bao gồm các loại dữ liệu sau:

- FAQ (Câu hỏi thường gặp)
- Emergency Contacts (Thông tin liên hệ khẩn cấp)
- Events (Sự kiện)
- About Pixity (Thông tin về Pixity)
- Solana Summit (Thông tin về Solana Summit)
- Da Nang Bucket List (Danh sách điểm đến ở Đà Nẵng)

Tất cả các endpoint đều được triển khai với khả năng cache để tối ưu hiệu suất.

## Cơ chế Cache

Hệ thống sử dụng TTLCache từ thư viện `cachetools` để lưu trữ tạm thời kết quả, giảm thiểu thời gian truy cập cơ sở dữ liệu. Mỗi loại dữ liệu có một cache riêng với thời gian sống (TTL) là 300 giây (5 phút).

## Base URL

```
/postgres
```

## Endpoints

### FAQ Endpoints

#### Lấy danh sách FAQ

```
GET /postgres/faq
```

**Tham số**

| Tên | Kiểu | Mô tả | Mặc định |
|-----|------|-------|----------|
| skip | integer | Số lượng item bỏ qua | 0 |
| limit | integer | Số lượng item tối đa trả về | 100 |
| active_only | boolean | Chỉ trả về các item đang hoạt động | false |
| use_cache | boolean | Sử dụng cache nếu có sẵn | true |

**Response**

Mảng các đối tượng FAQ:

```json
[
  {
    "question": "Làm thế nào để đặt phòng khách sạn?",
    "answer": "Bạn có thể đặt phòng khách sạn thông qua ứng dụng hoặc website của chúng tôi.",
    "is_active": true,
    "id": 1,
    "created_at": "2023-01-01T00:00:00",
    "updated_at": "2023-01-01T00:00:00"
  }
]
```

#### Tạo FAQ mới

```
POST /postgres/faq
```

**Request Body**

```json
{
  "question": "Làm thế nào để đặt phòng khách sạn?",
  "answer": "Bạn có thể đặt phòng khách sạn thông qua ứng dụng hoặc website của chúng tôi.",
  "is_active": true
}
```

**Response**

```json
{
  "question": "Làm thế nào để đặt phòng khách sạn?",
  "answer": "Bạn có thể đặt phòng khách sạn thông qua ứng dụng hoặc website của chúng tôi.",
  "is_active": true,
  "id": 1,
  "created_at": "2023-01-01T00:00:00",
  "updated_at": "2023-01-01T00:00:00"
}
```

#### Lấy thông tin một FAQ

```
GET /postgres/faq/{faq_id}
```

**Tham số**

| Tên | Kiểu | Mô tả | Mặc định |
|-----|------|-------|----------|
| faq_id | integer | ID của FAQ cần lấy | Required |
| use_cache | boolean | Sử dụng cache nếu có sẵn | true |

**Response**

```json
{
  "question": "Làm thế nào để đặt phòng khách sạn?",
  "answer": "Bạn có thể đặt phòng khách sạn thông qua ứng dụng hoặc website của chúng tôi.",
  "is_active": true,
  "id": 1,
  "created_at": "2023-01-01T00:00:00",
  "updated_at": "2023-01-01T00:00:00"
}
```

#### Cập nhật FAQ

```
PUT /postgres/faq/{faq_id}
```

**Tham số**

| Tên | Kiểu | Mô tả | Mặc định |
|-----|------|-------|----------|
| faq_id | integer | ID của FAQ cần cập nhật | Required |

**Request Body**

```json
{
  "question": "Cách đặt phòng khách sạn?",
  "answer": "Bạn có thể đặt phòng khách sạn thông qua ứng dụng hoặc website của chúng tôi.",
  "is_active": true
}
```

**Response**

```json
{
  "question": "Cách đặt phòng khách sạn?",
  "answer": "Bạn có thể đặt phòng khách sạn thông qua ứng dụng hoặc website của chúng tôi.",
  "is_active": true,
  "id": 1,
  "created_at": "2023-01-01T00:00:00",
  "updated_at": "2023-01-01T00:00:00"
}
```

#### Xóa FAQ

```
DELETE /postgres/faq/{faq_id}
```

**Tham số**

| Tên | Kiểu | Mô tả | Mặc định |
|-----|------|-------|----------|
| faq_id | integer | ID của FAQ cần xóa | Required |

**Response**

```json
{
  "status": "success",
  "message": "FAQ item 1 deleted"
}
```

#### Tạo nhiều FAQ cùng lúc

```
POST /postgres/faqs/batch
```

**Request Body**

```json
{
  "faqs": [
    {
      "question": "Câu hỏi 1?",
      "answer": "Trả lời 1",
      "is_active": true
    },
    {
      "question": "Câu hỏi 2?",
      "answer": "Trả lời 2",
      "is_active": true
    }
  ]
}
```

**Response**

Mảng các đối tượng FAQ đã tạo.

#### Cập nhật trạng thái của nhiều FAQ

```
PUT /postgres/faqs/batch-update-status
```

**Request Body**

```json
{
  "faq_ids": [1, 2, 3],
  "is_active": false
}
```

**Response**

```json
{
  "success_count": 3,
  "failed_ids": [],
  "message": "Updated 3 FAQ items"
}
```

#### Xóa nhiều FAQ

```
DELETE /postgres/faqs/batch
```

**Request Body**

```json
{
  "faq_ids": [1, 2, 3]
}
```

**Response**

```json
{
  "success_count": 3,
  "failed_ids": [],
  "message": "Deleted 3 FAQ items"
}
```

### Emergency Contact Endpoints

#### Lấy danh sách liên hệ khẩn cấp

```
GET /postgres/emergency
```

**Tham số**

| Tên | Kiểu | Mô tả | Mặc định |
|-----|------|-------|----------|
| skip | integer | Số lượng item bỏ qua | 0 |
| limit | integer | Số lượng item tối đa trả về | 100 |
| active_only | boolean | Chỉ trả về các item đang hoạt động | false |
| use_cache | boolean | Sử dụng cache nếu có sẵn | true |

**Response**

Mảng các đối tượng Emergency Contact.

#### Tạo Emergency Contact mới

```
POST /postgres/emergency
```

**Request Body**

```json
{
  "name": "Cứu hỏa",
  "phone_number": "114",
  "description": "Dịch vụ cứu hỏa",
  "address": "Đà Nẵng",
  "location": "16.0544, 108.2022",
  "priority": 1,
  "is_active": true
}
```

**Response**

Chi tiết Emergency Contact đã tạo.

#### Xem chi tiết Emergency Contact

```
GET /postgres/emergency/{emergency_id}
```

**Tham số**

| Tên | Kiểu | Mô tả | Mặc định |
|-----|------|-------|----------|
| emergency_id | integer | ID của Emergency Contact | Required |
| use_cache | boolean | Sử dụng cache nếu có sẵn | true |

**Response**

Chi tiết Emergency Contact.

#### Cập nhật Emergency Contact

```
PUT /postgres/emergency/{emergency_id}
```

**Tham số**

| Tên | Kiểu | Mô tả | Mặc định |
|-----|------|-------|----------|
| emergency_id | integer | ID của Emergency Contact | Required |

**Request Body**

```json
{
  "name": "Cứu hỏa Đà Nẵng",
  "phone_number": "114",
  "priority": 2
}
```

**Response**

Chi tiết Emergency Contact đã cập nhật.

#### Xóa Emergency Contact

```
DELETE /postgres/emergency/{emergency_id}
```

**Tham số**

| Tên | Kiểu | Mô tả | Mặc định |
|-----|------|-------|----------|
| emergency_id | integer | ID của Emergency Contact | Required |

**Response**

```json
{
  "status": "success",
  "message": "Emergency contact 1 deleted"
}
```

#### Tạo nhiều Emergency Contact

```
POST /postgres/emergency/batch
```

**Request Body**

```json
{
  "emergency_contacts": [
    {
      "name": "Cứu hỏa",
      "phone_number": "114",
      "priority": 1
    },
    {
      "name": "Cảnh sát",
      "phone_number": "113",
      "priority": 2
    }
  ]
}
```

**Response**

Mảng các Emergency Contact đã tạo.

#### Cập nhật trạng thái của nhiều Emergency Contact

```
PUT /postgres/emergency/batch-update-status
```

**Request Body**

```json
{
  "emergency_ids": [1, 2, 3],
  "is_active": false
}
```

**Response**

```json
{
  "success_count": 3,
  "failed_ids": [],
  "message": "Updated 3 emergency contacts"
}
```

#### Xóa nhiều Emergency Contact

```
DELETE /postgres/emergency/batch
```

**Request Body**

```json
{
  "emergency_ids": [1, 2, 3]
}
```

**Response**

```json
{
  "success_count": 3,
  "failed_ids": [],
  "message": "Deleted 3 emergency contacts"
}
```

### Event Endpoints

#### Lấy danh sách sự kiện

```
GET /postgres/events
```

**Tham số**

| Tên | Kiểu | Mô tả | Mặc định |
|-----|------|-------|----------|
| skip | integer | Số lượng item bỏ qua | 0 |
| limit | integer | Số lượng item tối đa trả về | 100 |
| active_only | boolean | Chỉ trả về các item đang hoạt động | false |
| featured_only | boolean | Chỉ trả về các item nổi bật | false |
| use_cache | boolean | Sử dụng cache nếu có sẵn | true |

**Response**

Mảng các đối tượng Event.

#### Tạo sự kiện mới

```
POST /postgres/events
```

**Request Body**

```json
{
  "name": "Lễ hội pháo hoa Đà Nẵng",
  "description": "Lễ hội pháo hoa quốc tế Đà Nẵng 2023",
  "address": "Cầu Rồng, Đà Nẵng",
  "location": "16.0610, 108.2277",
  "date_start": "2023-06-01T19:00:00",
  "date_end": "2023-06-01T22:00:00",
  "price": [
    {"type": "VIP", "amount": 500000},
    {"type": "Standard", "amount": 300000}
  ],
  "url": "https://danangfireworks.com",
  "is_active": true,
  "featured": true
}
```

**Response**

Chi tiết sự kiện đã tạo.

#### Xem chi tiết sự kiện

```
GET /postgres/events/{event_id}
```

**Tham số**

| Tên | Kiểu | Mô tả | Mặc định |
|-----|------|-------|----------|
| event_id | integer | ID của sự kiện | Required |
| use_cache | boolean | Sử dụng cache nếu có sẵn | true |

**Response**

Chi tiết sự kiện.

#### Cập nhật sự kiện

```
PUT /postgres/events/{event_id}
```

**Tham số**

| Tên | Kiểu | Mô tả | Mặc định |
|-----|------|-------|----------|
| event_id | integer | ID của sự kiện | Required |

**Request Body**

```json
{
  "name": "Lễ hội pháo hoa quốc tế Đà Nẵng",
  "featured": true
}
```

**Response**

Chi tiết sự kiện đã cập nhật.

#### Xóa sự kiện

```
DELETE /postgres/events/{event_id}
```

**Tham số**

| Tên | Kiểu | Mô tả | Mặc định |
|-----|------|-------|----------|
| event_id | integer | ID của sự kiện | Required |

**Response**

```json
{
  "status": "success",
  "message": "Event 1 deleted"
}
```

#### Tạo nhiều sự kiện

```
POST /postgres/events/batch
```

**Request Body**

```json
{
  "events": [
    {
      "name": "Sự kiện 1",
      "description": "Mô tả sự kiện 1",
      "address": "Địa chỉ 1",
      "date_start": "2023-06-01T19:00:00",
      "is_active": true
    },
    {
      "name": "Sự kiện 2",
      "description": "Mô tả sự kiện 2",
      "address": "Địa chỉ 2",
      "date_start": "2023-07-01T19:00:00",
      "is_active": true
    }
  ]
}
```

**Response**

Mảng các sự kiện đã tạo.

#### Cập nhật trạng thái của nhiều sự kiện

```
PUT /postgres/events/batch-update-status
```

**Request Body**

```json
{
  "event_ids": [1, 2, 3],
  "is_active": false
}
```

**Response**

```json
{
  "success_count": 3,
  "failed_ids": [],
  "message": "Updated 3 events"
}
```

#### Xóa nhiều sự kiện

```
DELETE /postgres/events/batch
```

**Request Body**

```json
{
  "event_ids": [1, 2, 3]
}
```

**Response**

```json
{
  "success_count": 3,
  "failed_ids": [],
  "message": "Deleted 3 events"
}
```

### About Pixity Endpoints

#### Lấy thông tin về Pixity

```
GET /postgres/about-pixity
```

**Tham số**

| Tên | Kiểu | Mô tả | Mặc định |
|-----|------|-------|----------|
| use_cache | boolean | Sử dụng cache nếu có sẵn | true |

**Response**

```json
{
  "content": "PiXity is your smart, AI-powered local companion...",
  "id": 1,
  "created_at": "2023-01-01T00:00:00",
  "updated_at": "2023-01-01T00:00:00"
}
```

#### Cập nhật thông tin về Pixity

```
PUT /postgres/about-pixity
```

**Request Body**

```json
{
  "content": "PiXity is your smart, AI-powered local companion..."
}
```

**Response**

```json
{
  "content": "PiXity is your smart, AI-powered local companion...",
  "id": 1,
  "created_at": "2023-01-01T00:00:00",
  "updated_at": "2023-01-01T00:00:00"
}
```

### Da Nang Bucket List Endpoints

#### Lấy thông tin Da Nang Bucket List

```
GET /postgres/danang-bucket-list
```

**Tham số**

| Tên | Kiểu | Mô tả | Mặc định |
|-----|------|-------|----------|
| use_cache | boolean | Sử dụng cache nếu có sẵn | true |

**Response**

```json
{
  "content": "{\"title\":\"Da Nang Bucket List\",\"description\":\"Must-visit places and experiences in Da Nang\",\"items\":[...]}",
  "id": 1,
  "created_at": "2023-01-01T00:00:00",
  "updated_at": "2023-01-01T00:00:00"
}
```

#### Cập nhật Da Nang Bucket List

```
PUT /postgres/danang-bucket-list
```

**Request Body**

```json
{
  "content": "{\"title\":\"Da Nang Bucket List\",\"description\":\"Must-visit places and experiences in Da Nang\",\"items\":[...]}"
}
```

**Response**

```json
{
  "content": "{\"title\":\"Da Nang Bucket List\",\"description\":\"Must-visit places and experiences in Da Nang\",\"items\":[...]}",
  "id": 1,
  "created_at": "2023-01-01T00:00:00",
  "updated_at": "2023-01-01T00:00:00"
}
```

### Solana Summit Endpoints

#### Lấy thông tin Solana Summit

```
GET /postgres/solana-summit
```

**Tham số**

| Tên | Kiểu | Mô tả | Mặc định |
|-----|------|-------|----------|
| use_cache | boolean | Sử dụng cache nếu có sẵn | true |

**Response**

```json
{
  "content": "{\"title\":\"Solana Summit Vietnam\",\"description\":\"Information about Solana Summit Vietnam event in Da Nang\",\"date\":\"2023-11-04T09:00:00+07:00\",\"location\":\"Hyatt Regency, Da Nang\",\"details\":\"The Solana Summit is a gathering of developers, entrepreneurs, and enthusiasts in the Solana ecosystem.\",\"agenda\":[...],\"registration_url\":\"https://example.com/solana-summit-registration\"}",
  "id": 1,
  "created_at": "2023-01-01T00:00:00",
  "updated_at": "2023-01-01T00:00:00"
}
```

#### Cập nhật Solana Summit

```
PUT /postgres/solana-summit
```

**Request Body**

```json
{
  "content": "{\"title\":\"Solana Summit Vietnam\",\"description\":\"Information about Solana Summit Vietnam event in Da Nang\",\"date\":\"2023-11-04T09:00:00+07:00\",\"location\":\"Hyatt Regency, Da Nang\",\"details\":\"The Solana Summit is a gathering of developers, entrepreneurs, and enthusiasts in the Solana ecosystem.\",\"agenda\":[...],\"registration_url\":\"https://example.com/solana-summit-registration\"}"
}
```

**Response**

```json
{
  "content": "{\"title\":\"Solana Summit Vietnam\",\"description\":\"Information about Solana Summit Vietnam event in Da Nang\",\"date\":\"2023-11-04T09:00:00+07:00\",\"location\":\"Hyatt Regency, Da Nang\",\"details\":\"The Solana Summit is a gathering of developers, entrepreneurs, and enthusiasts in the Solana ecosystem.\",\"agenda\":[...],\"registration_url\":\"https://example.com/solana-summit-registration\"}",
  "id": 1,
  "created_at": "2023-01-01T00:00:00",
  "updated_at": "2023-01-01T00:00:00"
}
```

### Health Check Endpoint

#### Kiểm tra tình trạng PostgreSQL

```
GET /postgres/health
```

**Response**

```json
{
  "status": "healthy",
  "message": "PostgreSQL connection is working",
  "timestamp": "2023-01-01T00:00:00"
}
```

## Mã lỗi

| Mã lỗi | Mô tả |
|--------|-------|
| 400 | Bad Request - Yêu cầu không hợp lệ |
| 404 | Not Found - Không tìm thấy tài nguyên |
| 500 | Internal Server Error - Lỗi máy chủ nội bộ |
| 503 | Service Unavailable - Dịch vụ không khả dụng |

## Lưu ý về Cache

1. Tất cả các endpoint GET đều hỗ trợ tham số `use_cache` để bật/tắt caching.
2. Cache được tự động làm mới khi có thay đổi dữ liệu (thông qua các endpoint POST, PUT, DELETE).
3. TTL mặc định cho tất cả các cache là 300 giây (5 phút).
4. Đối với endpoints lấy danh sách (list), cache key được tạo dựa trên tham số query để đảm bảo các bộ lọc khác nhau được cache riêng biệt. 