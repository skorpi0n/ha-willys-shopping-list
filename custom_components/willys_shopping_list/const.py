"""Constants for the Willys shopping list integration."""

DOMAIN = "willys_shopping_list"

BASE_URL = "https://www.willys.se"
CSRF_PATH = "/axfood/rest/v2/csrf-token"
LISTS_PATH = "/axfood/rest/v2/user-wishlist"
CUSTOMER_PATH = "/axfood/rest/v2/customer"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"

SERVICE_GET_LISTS = "get_lists"
SERVICE_GET_LIST = "get_list"
SERVICE_CREATE_LIST = "create_list"
SERVICE_DELETE_LIST = "delete_list"
SERVICE_ADD_PRODUCT = "add_product"
SERVICE_REMOVE_PRODUCT = "remove_product"
SERVICE_CHANGE_QUANTITY = "change_quantity"

ATTR_LIST_ID = "list_id"
ATTR_PRODUCT_CODE = "product_code"
ATTR_QUANTITY = "quantity"
ATTR_DELTA = "delta"
ATTR_PICK_UNIT = "pick_unit"
ATTR_NAME = "name"
