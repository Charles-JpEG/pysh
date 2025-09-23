# module for command execution

import subprocess
from groups import Group, OperatorGroup, CommandGroup

def run(args: list[str]):
    if args[0] in builtin_commands:
        pass    # TODO
    else:
        ret = subprocess.run(args)
        return ret.returncode
     

def parse(groups: list[Group]) -> None:
    i = 0
    while i < len(groups):
        g = groups[i]
        if isinstance(g, OperatorGroup):
            # syntax error, but just ignore that
            i += 1
            continue
        else:
            if i + 1 < len(groups) and isinstance(groups[i + 1], OperatorGroup):
                match groups[i + 1].op:
                    case '&':
                        bgCmds.add_cmd(g)
                        i += 1
                    case "&&":
                        run(g)
                        
                        


class BgCommands:
    pendingCommands: set[CommandGroup] = []
    runningCommands = []
    def __init__(self):
        pass

    def add_cmd(self, group: CommandGroup) -> None:
        self.pendingCommands.add(group)


class Queue:
    def __init__(self):
        pass

    commands: list[CommandGroup] = []

    def add_cmd(self, group: CommandGroup) -> None:
        self.commands.append(group)

builtin_commands = {}
queue = Queue()
bgCmds = BgCommands()