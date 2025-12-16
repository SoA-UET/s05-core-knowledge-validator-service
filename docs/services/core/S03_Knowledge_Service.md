# Telcenter Core - Knowledge Service (S03)

Introducing the series of Telcenter Engineering.

Telcenter, on the surface, is a semi-automated telecom services call center -
it is a web app that offers telecommunication services consultation. People
are serviced by the AI Agent, and they will be forwarded to in-person
consultants if the AI detected down mood, rage, or that it could not answer
the question itself given a pre-fed ground truth database. Now, we are
designing this as microservices. Telcenter Core would act as the main backend
for the end-user interface, and it consists of multiple microservices.
Telcenter Partner is another system that is deployed separately on each of
the telecom partner's servers, and it is responsible for taking up forwarded
conversations and continuing them with the real persons in-charge. Together,
one Core and several Partner systems cooperate to deliver the best customer
experience, while lowering cost dramatically, with the help of automated AI
responses.

The general deployment and communication topology is like this:

    Core <---(Internet)---> (Partner_1, Partner_2..., Partner_N)

The users' inquiries and answers to those are primarily in Vietnamese.

Now, you are designing the **Knowledge Service** service, in Python.
This service is inside the **Telcenter Core** system.

Here are the peer services that the **Knowledge Service** service may interact with:

- **S02 Consultant AI Agent**: The AI agent that handles customer conversations and queries the knowledge base for relevant information
- **S05 Knowledge Validator Service**: Validates and approves knowledge updates before they are stored in the knowledge database
- **S11 Partner Local Knowledge Service**: Receives metrics from partner services about knowledge queries

## A Note on API Transport Layers

The APIs of the services (including this one
and the peers) might be based on HTTP and/or
RabbitMQ transport protocols. One service might
also exposes multiple APIs of different kinds.

HTTP is mostly used in APIs that are exposed
to the frontend web apps, though it occasionally
is used for internal communication between
microservices, too. HTTP APIs are somewhat
RESTful (it is CRUD, stateless, versioned,
and HATEOAS, but it need not follow
Code-on-Demand requirements.)

For APIs that are based on RabbitMQ transport,
each API usually demands two queues, the
requests queue and the responses queue. The
caller would send requests into the former queue
and expect the responses to come out from the
latter. Exceptions will be explicitly noted.
The default queue names will be specified for
each such API. The queue names should be configurable
via `.env`, too.

## Peer Service APIs

Note that the base URL to call the services
must be specified via `.env`. Construct
a `.env.example` file for that.

### S02 Consultant AI Agent

[A01](../../api_groups/A01.md) - Send validated knowledge updates to the AI Agent whenever knowledge is updated

### S05 Knowledge Validator Service

[A08](../../api_groups/A08.md) - Receives validated knowledge from S05 for storage

## The Flow

### Main Flow: Store Validated Knowledge

Steps:

1. S05 Knowledge Validator Service sends validated knowledge data
   to S03 via RabbitMQ (using API A08). The event includes
   the SeaweedFS file ID where the knowledge data is stored.
2. S03 retrieves the knowledge data from SeaweedFS using the provided 
   file ID.
3. S03 processes the knowledge data and stores it into its
   internal database (MongoDB).
4. S03 sends the updated knowledge to S02 Consultant AI Agent
   via API A01 to update the AI's knowledge base.

If it fails at any stage, the whole process fails.
That is, immediately return error with the
appropriate error message.

## This Service's APIs

This service exposes the following APIs:

- [A08](../../api_groups/A08.md) - Receives validated knowledge from S05 (RabbitMQ)

## Technology

- Python
- Use `uv` as the virtual environment and package manager.
- Multithreaded logic should be used for performance, since this
    component relies a lot on other services, which means the API calls
    to those services take up very much time. So this service is I/O bound.
    Note that, using multithreading to emulate async operations is very
    important - but do NOT use `async` and `await` in Python - that would
    be a mess!

- The class `MessageQueueService` must be used for RabbitMQ communication (which internally
    use `pika`).

    The class is [located in this file](../../../app/services/MessageQueueService.py).

    An example of using this class [is given here](../../MessageQueueService-usage-example.py).

    Also, for multithreading, only use the scheme in that file.
    Any other use of multithreading, if necessary, must strictly
    look for hazards - use locks and other synchronization primitives
    where appropriate.

- If this service needs to expose HTTP API(s), use Flask.

- The program entry point is [in this file](../../../app/__main__.py).

## Database Schema (MongoDB)

### Collection: `packages` (Gói cước)

Lưu thông tin các gói cước viễn thông từ tất cả các Partner.

Fields:

- `id` (ObjectId, Primary Key): ID của gói cước
- `partner_id` (string): ID của partner sở hữu gói cước
- `Mã dịch vụ` (string): Mã dịch vụ gói cước
- `Thời gian thanh toán` (string): Hình thức thanh toán (trả trước/trả sau)
- `Các dịch vụ tiên quyết` (string): Các dịch vụ cần có để đăng ký gói cước
- `Giá (VNĐ)` (number): Giá gói cước (VNĐ)
- `Chu kỳ (ngày)` (number): Chu kỳ gói cước (ngày)
- `4G tốc độ tiêu chuẩn/ngày` (number): Dung lượng 4G tốc độ tiêu chuẩn mỗi ngày (GB)
- `4G tốc độ cao/ngày` (number): Dung lượng 4G tốc độ cao mỗi ngày (GB)
- `4G tốc độ tiêu chuẩn/chu kỳ` (number): Dung lượng 4G tốc độ tiêu chuẩn mỗi chu kỳ (GB)
- `4G tốc độ cao/chu kỳ` (number): Dung lượng 4G tốc độ cao mỗi chu kỳ (GB)
- `Gọi nội mạng` (string): Thông tin gọi nội mạng
- `Gọi ngoại mạng` (string): Thông tin gọi ngoại mạng
- `Tin nhắn` (string): Thông tin tin nhắn
- `Chi tiết` (string): Thông tin chi tiết gói cước
- `Tự động gia hạn` (string): Thông tin về tự động gia hạn
- `Cú pháp đăng ký` (string): Cú pháp đăng ký gói cước

### Collection: `faqs` (Câu hỏi thường gặp)

Lưu các câu hỏi và câu trả lời từ tất cả các Partner.

Fields:

- `id` (ObjectId, Primary Key): ID của câu hỏi
- `partner_id` (string): ID của partner sở hữu câu hỏi
- `question` (string): Nội dung câu hỏi thường gặp
- `answer` (string): Nội dung câu trả lời chuẩn

Sample `faqs` document:

```json
{
    "id": "...",
    "partner_id": 1,
    "question": "Làm sao để kiểm tra số dư?",
    "answer": "Bấm *101# để kiểm tra số dư tài khoản."
}
```
