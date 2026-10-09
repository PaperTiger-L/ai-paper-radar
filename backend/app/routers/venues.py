"""会议 / 期刊清单：供用户管理界面选择"关注的会议或期刊"。"""
from fastapi import APIRouter, Depends

from .. import schemas
from ..deps import get_current_user

router = APIRouter(prefix="/api/venues", tags=["venues"])

CONFERENCES = [
    "NeurIPS", "ICML", "ICLR", "CVPR", "ICCV", "ECCV",
    "ACL", "EMNLP", "NAACL", "AAAI", "IJCAI", "KDD", "WWW", "SIGIR",
    "CHI", "SIGMOD", "VLDB", "ICDE", "OSDI", "SOSP",
    "MICCAI", "RSS", "CoRL", "ICRA", "IROS", "AISTATS", "UAI",
    "COLT", "STOC", "FOCS", "SODA", "WSDM", "RecSys",
]

JOURNALS = [
    "Nature", "Science", "TPAMI", "TIP", "TNNLS", "TKDE",
    "JMLR", "IJCV", "TACL", "TKDD", "TOIS", "TMC", "TSC",
    "Cell", "Nature Machine Intelligence", "Science Robotics",
]


@router.get("", response_model=schemas.VenuesOut)
def list_venues(_user: str = Depends(get_current_user)):
    """返回顶会 / 顶刊清单（静态配置）。"""
    return {"conferences": CONFERENCES, "journals": JOURNALS}
