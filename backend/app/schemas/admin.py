from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class InstallationOut(BaseModel):
    id: int
    slug: str
    name: str
    lat: Optional[float]
    lng: Optional[float]
    group_name: Optional[str]
    is_active: bool
    notes: Optional[str]

    model_config = {"from_attributes": True}


class InstallationPatch(BaseModel):
    name: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    group_name: Optional[str] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


class DeviceOut(BaseModel):
    id: int
    imei: str
    model: Optional[str]
    is_active: bool

    model_config = {"from_attributes": True}


class MenuInstallation(BaseModel):
    slug: str
    name: str
    group_name: Optional[str]
    status: str  # 'online' | 'offline' | 'alert'
    is_active: bool
