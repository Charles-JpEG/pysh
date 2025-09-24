# Spec for pysh

## Guaranteed shell commands to preserve
- cd ls pwd mkdir rmdir rm cp mv find basename dirname
- echo cat head tail wc grep sort uniq cut
- date uname ps which env
- fd rg

### Hints:
- All variables are managed by python, including shell env variables. Access them as if you're writing in python, or if need string repr, use $var instead
- grep would enable Perl mode (-P) by default, use -G to use BRE