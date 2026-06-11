# -*- coding: utf-8 -*-


class ProductType:
    LUMP = "lump"

    LUMP_LABEL = "Lump"

    SELECTION = [
        (LUMP, LUMP_LABEL),
    ]

    MODEL = {
        LUMP: "wt.weighing.lump",
    }

    STOCK_QUANTITY_FIELD = {
        LUMP: "net_weight",
    }

    TRANSLATION_TERMS = (
        LUMP_LABEL,
    )
