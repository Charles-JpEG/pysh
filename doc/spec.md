# Spec for pysh

## Commands
pysh uses shell commands in PATH. If not found, it would look for variables and behave like python in interactive mode. For example
```pysh
> pwd
/home/danel
> date
Thu 25 Sep 2025 20:28:49 AEST
> date = '11:05'
<TODO: Placeholder for error msg>
> date
Thu 25 Sep 2025 20:28:57 AEST   # date command is preserved and protected
```


## Variables
All variables, including environment variables, are managed by python. This is one of the core features of pysh.
- Traditional method like $var would still be prased into string, but it's also a python string. 
- pysh also holds generic python variables, to access them, simply write python code


## Guaranteed shell commands
these commands are well tested and should work fine
- cd ls pwd mkdir rmdir rm cp mv find basename dirname
- echo cat head tail wc grep sort uniq cut
- date uname ps which env
- fd rg

### Hints:
- All variables are managed by python, including shell env variables. Access them as if you're writing in python, or if need string repr, use $var instead
- grep would enable Perl mode (-P) by default, use -G to use BRE
