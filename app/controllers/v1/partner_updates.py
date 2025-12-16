"""
H22 HTTP Controller for Partner Updates.

Provides REST API endpoints for Core Portal to manage partner knowledge updates:
- GET /api/v1/partner-updates - List updates
- GET /api/v1/partner-updates/{update_id} - Get update details
- POST /api/v1/partner-updates/{update_id}/approve - Approve update
- POST /api/v1/partner-updates/{update_id}/reject - Reject update
"""

from flask import request, g
from flask_restx import Namespace, Resource, fields, reqparse

from ...utils.auth import auth_required
from ...services.validation_task_service import validation_task_service

#######################################
## STEP 1. DECLARE THE API NAMESPACE ##
#######################################

api = Namespace(
    "partner-updates",
    description="Quản lý các bản cập nhật kiến thức từ Partner để duyệt.",
)

####################################
## STEP 2. DEFINE THE MODELS/DTOs ##
####################################

# Update summary in list response
update_summary_dto = api.model(
    "UpdateSummary",
    {
        "id": fields.String(description="ID của bản cập nhật"),
        "partner_id": fields.String(description="ID của partner gửi cập nhật"),
        "status": fields.String(
            description="Trạng thái: pending, approved, rejected",
            enum=["pending", "approved", "rejected"],
        ),
        "validator_id": fields.String(
            description="ID người duyệt (null nếu chưa duyệt)", allow_null=True
        ),
        "created_at": fields.String(description="Thời gian tạo (ISO 8601)"),
        "validated_at": fields.String(
            description="Thời gian duyệt (ISO 8601)", allow_null=True
        ),
    },
)

# Summary counts
summary_counts_dto = api.model(
    "SummaryCounts",
    {
        "total": fields.Integer(description="Tổng số bản cập nhật"),
        "pending": fields.Integer(description="Số bản chờ duyệt"),
        "approved": fields.Integer(description="Số bản đã duyệt"),
        "rejected": fields.Integer(description="Số bản bị từ chối"),
    },
)

# List response
updates_list_response_dto = api.model(
    "UpdatesListResponse",
    {
        "status": fields.String(description="success"),
        "total_count": fields.Integer(description="Tổng số kết quả"),
        "page": fields.Integer(description="Số trang hiện tại"),
        "limit": fields.Integer(description="Số items mỗi trang"),
        "total_pages": fields.Integer(description="Tổng số trang"),
        "updates": fields.List(
            fields.Nested(update_summary_dto), description="Danh sách bản cập nhật"
        ),
        "summary": fields.Nested(summary_counts_dto, description="Thống kê tổng hợp"),
    },
)

# FAQ model
faq_dto = api.model(
    "FAQ",
    {
        "question": fields.String(description="Câu hỏi"),
        "answer": fields.String(description="Câu trả lời"),
    },
)

# Package model
package_dto = api.model(
    "Package",
    {
        "Mã dịch vụ": fields.String(description="Mã dịch vụ"),
        "Thời gian thanh toán": fields.String(description="Hình thức thanh toán"),
        "Các dịch vụ tiên quyết": fields.String(description="Dịch vụ tiên quyết"),
        "Giá (VNĐ)": fields.Integer(description="Giá (VNĐ)"),
        "Chu kỳ (ngày)": fields.Integer(description="Chu kỳ (ngày)"),
        "4G tốc độ tiêu chuẩn/ngày": fields.Float(description="4G tiêu chuẩn/ngày (GB)"),
        "4G tốc độ cao/ngày": fields.Float(description="4G tốc độ cao/ngày (GB)"),
        "4G tốc độ tiêu chuẩn/chu kỳ": fields.Float(description="4G tiêu chuẩn/chu kỳ (GB)"),
        "4G tốc độ cao/chu kỳ": fields.Float(description="4G tốc độ cao/chu kỳ (GB)"),
        "Gọi nội mạng": fields.String(description="Thông tin gọi nội mạng"),
        "Gọi ngoại mạng": fields.String(description="Thông tin gọi ngoại mạng"),
        "Tin nhắn": fields.String(description="Thông tin tin nhắn"),
        "Chi tiết": fields.String(description="Chi tiết gói cước"),
        "Tự động gia hạn": fields.String(description="Tự động gia hạn"),
        "Cú pháp đăng ký": fields.String(description="Cú pháp đăng ký"),
    },
)

# Update detail with FAQs and packages
update_detail_dto = api.model(
    "UpdateDetail",
    {
        "id": fields.String(description="ID của bản cập nhật"),
        "partner_id": fields.String(description="ID của partner gửi cập nhật"),
        "status": fields.String(description="Trạng thái"),
        "validator_id": fields.String(description="ID người duyệt", allow_null=True),
        "created_at": fields.String(description="Thời gian tạo (ISO 8601)"),
        "validated_at": fields.String(description="Thời gian duyệt (ISO 8601)", allow_null=True),
        "faqs": fields.List(fields.Nested(faq_dto), description="Danh sách FAQ"),
        "packages": fields.List(fields.Nested(package_dto), description="Danh sách gói cước"),
    },
)

# Detail response
update_detail_response_dto = api.model(
    "UpdateDetailResponse",
    {
        "status": fields.String(description="success"),
        "update": fields.Nested(update_detail_dto, description="Chi tiết bản cập nhật"),
    },
)

# Action response (approve/reject)
update_action_response_dto = api.model(
    "UpdateActionResponse",
    {
        "status": fields.String(description="success"),
        "update": fields.Nested(update_summary_dto, description="Thông tin bản cập nhật sau khi xử lý"),
    },
)

# Error response
error_response_dto = api.model(
    "ErrorResponse",
    {
        "status": fields.String(description="error"),
        "message": fields.String(description="Thông báo lỗi"),
    },
)

###################################
## STEP 3. DEFINE THE CONTROLLER ##
###################################

# Query parser for list endpoint
list_parser = reqparse.RequestParser()
list_parser.add_argument(
    "status",
    type=str,
    required=False,
    choices=["pending", "approved", "rejected"],
    help="Filter by status",
)
list_parser.add_argument(
    "partner_id", type=str, required=False, help="Filter by partner ID"
)
list_parser.add_argument(
    "pageNumber", type=int, required=False, default=1, help="Page number (1-indexed)"
)
list_parser.add_argument(
    "pageSize", type=int, required=False, default=20, help="Items per page (max 100)"
)


@api.route("/")
class PartnerUpdatesList(Resource):
    """Partner updates list resource."""

    @api.doc(
        description="Lấy danh sách các bản cập nhật kiến thức từ Partner. Yêu cầu xác thực JWT.",
        security="Bearer Auth",
    )
    @api.expect(list_parser)
    @api.response(200, "Success", updates_list_response_dto)
    @api.response(401, "Unauthorized", error_response_dto)
    @auth_required
    def get(self):
        """Get list of partner updates."""
        args = list_parser.parse_args()

        result = validation_task_service.get_updates_list(
            status=args.get("status"),
            partner_id=args.get("partner_id"),
            page=args.get("pageNumber", 1),
            limit=args.get("pageSize", 20),
        )

        return result, 200


@api.route("/<string:update_id>")
class PartnerUpdateDetail(Resource):
    """Partner update detail resource."""

    @api.doc(
        description="Lấy chi tiết một bản cập nhật kiến thức. Yêu cầu xác thực JWT.",
        security="Bearer Auth",
    )
    @api.response(200, "Success", update_detail_response_dto)
    @api.response(401, "Unauthorized", error_response_dto)
    @api.response(404, "Not Found", error_response_dto)
    @auth_required
    def get(self, update_id: str):
        """Get update details."""
        result = validation_task_service.get_update_details(update_id)

        if result is None:
            return {"status": "error", "message": "Update not found"}, 404

        return result, 200


@api.route("/<string:update_id>/approve")
class PartnerUpdateApprove(Resource):
    """Partner update approve resource."""

    @api.doc(
        description="Duyệt một bản cập nhật kiến thức từ Partner. Yêu cầu xác thực JWT.",
        security="Bearer Auth",
    )
    @api.response(200, "Success", update_action_response_dto)
    @api.response(401, "Unauthorized", error_response_dto)
    @api.response(404, "Not Found", error_response_dto)
    @api.response(400, "Bad Request", error_response_dto)
    @auth_required
    def post(self, update_id: str):
        """Approve a partner update."""
        validator_id = g.user_id

        result = validation_task_service.approve_update(update_id, validator_id)

        if result is None:
            return {"status": "error", "message": "Update not found"}, 404

        if "error" in result:
            return {"status": "error", "message": result["error"]}, 400

        return result, 200


@api.route("/<string:update_id>/reject")
class PartnerUpdateReject(Resource):
    """Partner update reject resource."""

    @api.doc(
        description="Từ chối một bản cập nhật kiến thức từ Partner. Yêu cầu xác thực JWT.",
        security="Bearer Auth",
    )
    @api.response(200, "Success", update_action_response_dto)
    @api.response(401, "Unauthorized", error_response_dto)
    @api.response(404, "Not Found", error_response_dto)
    @api.response(400, "Bad Request", error_response_dto)
    @auth_required
    def post(self, update_id: str):
        """Reject a partner update."""
        validator_id = g.user_id

        result = validation_task_service.reject_update(update_id, validator_id)

        if result is None:
            return {"status": "error", "message": "Update not found"}, 404

        if "error" in result:
            return {"status": "error", "message": result["error"]}, 400

        return result, 200
