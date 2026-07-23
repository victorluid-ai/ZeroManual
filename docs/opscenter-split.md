# OpsCenter split notes

ZeroManual ya no incluye el runtime multiagente. Copia local generada durante el split:

- `/home/ubuntu/OpsCenter` (git local)
- `/opt/cursor/artifacts/OpsCenter` (artefacto del agente)

Publica el repo remoto cuando tengas permisos:

```bash
cd /home/ubuntu/OpsCenter
gh repo create victorluid-ai/OpsCenter --private --source=. --remote=origin --push
```

O crea el repo vacío en GitHub y:

```bash
cd /home/ubuntu/OpsCenter
git remote add origin git@github.com:victorluid-ai/OpsCenter.git
git push -u origin master
```
