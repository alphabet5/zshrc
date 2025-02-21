rem()
{
a=$(ssh dev 'find ~/GitHub/ -type d -maxdepth 1 | awk '"'"'{ print length($0) " " $0; }'"'"' $file | sort -n | cut -d " " -f 2- | grep -m 1 '$1'')
echo $a | xargs -t code --remote "ssh-remote+dev"
}
v()
{
  find /Users/$(whoami)/Documents/GitHub/ -type d -maxdepth 1 | awk '{ print length($0) " " $0; }' $file | sort -n | cut -d ' ' -f 2- | grep -m 1 $query | xargs -t code
}

c()
{
  find /Users/$(whoami)/Documents/GitHub/ -type d -maxdepth 1 | awk '{ print length($0) " " $0; }' $file | sort -n | cut -d ' ' -f 2- | grep -m 1 $query | xargs -t code
}
