# -*- coding: utf-8 -*-


class ProductType:
    CUP_LUMP = "cup_lump"

    CUP_LUMP_LABEL = "Cup Lump"

    SELECTION = [
        (CUP_LUMP, CUP_LUMP_LABEL),
    ]

    MODEL = {
        CUP_LUMP: "wt.weighing.cup.lump",
    }

    STOCK_QUANTITY_FIELD = {
        CUP_LUMP: "net_weight",
    }

    TRANSLATION_TERMS = (
        CUP_LUMP_LABEL,
    )
