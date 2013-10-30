# -*- coding: utf-8 -*-
from __future__ import absolute_import
from flask import Flask


class DisambigApp(Flask):

    def select_jinja_autoescape(self, filename):
        if filename and filename.endswith('.jinja2'):
            return True
        return Flask.select_jinja_autoescape(self, filename)

