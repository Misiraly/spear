import constants as cv
import yaml
import reader as rd


class Cabinet:
    def __init__(self):
        self.song = {}
        self.timeline = []
        self.pos = 0