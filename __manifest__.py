# -*- coding: utf-8 -*-
{
    "name": "WeighTrack",
    "version": "19.0.1.0.0",
    "category": "Operations/Inventory",
    "summary": "Recording and Tracking Anything Weighed",
    "author": "Fariz Rizky Tanjung",
    "license": "LGPL-3",
    "depends": ["base", "mail"],
    "data": [
        "security/access_groups.xml",
        "security/ir.model.access.csv",

        "views/weighing_type_views.xml",
        "views/weighing_method_views.xml",

        "views/menu.xml",
    ],
    "application": True,
    "installable": True,
}
