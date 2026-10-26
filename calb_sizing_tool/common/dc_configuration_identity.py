"""Explicit catalogue terms for the limited 20ft configuration pilot."""
import re


def is_20ft_container_type(value):
    """Recognise existing catalogue labels, never infer from dimensions or names."""
    if not isinstance(value, str):
        return False
    token = re.sub(r'[\s_-]+', '', value.strip().lower())
    return token in {
        '20ft', '20foot', '20feet', '20ftcontainer', '20ftisocontainer',
        '20ftdccontainer', '20footcontainer', '20feetcontainer',
    }
