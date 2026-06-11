# -*- coding: utf-8 -*-


class Role:
    OPERATOR = "operator"
    CLERK = "clerk"
    FOREMAN = "foreman"
    TAPPER = "tapper"

    OPERATOR_LABEL = "Operator"
    CLERK_LABEL = "Clerk"
    FOREMAN_LABEL = "Foreman"
    TAPPER_LABEL = "Tapper"

    SELECTION = [
        (OPERATOR, OPERATOR_LABEL),
        (CLERK, CLERK_LABEL),
        (FOREMAN, FOREMAN_LABEL),
        (TAPPER, TAPPER_LABEL),
    ]

    DEVICE_SELECTION = [
        (CLERK, CLERK_LABEL),
        (FOREMAN, FOREMAN_LABEL),
        (OPERATOR, OPERATOR_LABEL),
    ]

    VALUES = tuple(role for role, _label in SELECTION)
    DEVICE_VALUES = tuple(role for role, _label in DEVICE_SELECTION)
    TRANSLATION_TERMS = (
        OPERATOR_LABEL,
        CLERK_LABEL,
        FOREMAN_LABEL,
        TAPPER_LABEL,
    )
