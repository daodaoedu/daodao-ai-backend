root@localhost:~# df -h /
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda         49G   34G   13G  73% /
root@localhost:~# docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}'
REPOSITORY          TAG                                            SIZE
vincentxxx/app      dev-32f5045827b4341db169361cfa8c2164b431b34b   878MB
daodao-ai-backend   latest                                         7.94GB
redis               alpine                                         70.6MB
vincentxxx/app      prod                                           1.31GB
n8nio/n8n           1.104.2                                        1.02GB
redis               6                                              106MB
postgres            14                                             422MB
nginx               latest                                         188MB
mongo               4.4                                            427MB
qdrant/qdrant       v1.7.3                                         157MB


專案image太大，需要檢查是否有優化空間