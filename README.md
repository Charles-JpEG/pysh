# pysh
Combine python3 and posix shell

## Overview
The purpose of pysh is to have python running like a shell, take advantage of CLI tools and python features at the same time.

## Dependencies
- At least one posix compliant shell
- Python3

## Example usage
```pysh
$ pysh
>> cd ~/Projects/demo
>> cat users.psv
Alex | 1
Ben | 2
Cindy | 3
David | 4
Emma | 5
>> users = [line.strip() for line in $(cat users.psv)]
>> for user in users:
...    match = re.match(r"^(\w+)\s\|", user)
...    if match:
...        print(match.group(1))
```
