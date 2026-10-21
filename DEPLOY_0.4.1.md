# FaceRec v0.4.1 — VPN-safe Docker network hotfix

The prior Compose file allowed Docker to assign `172.20.0.0/16` to `facerec-internal`. That overlaps the office VPN remote network. v0.4.1 pins FaceRec to the Docker-only `198.18.254.0/28` subnet.

This procedure does not change or restart the host network interfaces, routes, NetworkManager, VPN, or any non-FaceRec Docker project. The `facerec-db` volume is preserved.

Connect directly to `<HYPERVISOR_IP>` without VPN while repairing the collision.

```bash
cd /opt/facerec

# Remove only the currently broken FaceRec containers/network.
# Do not use -v.
docker compose down --remove-orphans

# The Docker-created 172.20 route must now be absent.
ip -4 route show 172.20.0.0/16

cp -a compose.yaml compose.yaml.before-vpn-safe-network-20260831.bak

sudo tar -xzf ~/Documents/FaceRec_Phase4_Admin_Privacy_0.4.1.tar.gz \
  -C /opt/facerec

sudo chown -R <deploy-user>:<deploy-user> /opt/facerec

# Verify the fixed subnet before Docker creates anything.
sed -n '/^networks:/,/^volumes:/p' compose.yaml
docker compose config --quiet

docker compose up -d

for attempt in {1..30}; do
  curl -fsS http://127.0.0.1:8091/api/health >/dev/null && break
  sleep 2
done

docker compose ps
docker network inspect facerec-internal \
  --format '{{range .IPAM.Config}}{{.Subnet}} gateway={{.Gateway}}{{end}}'

ip -4 route show 172.20.0.0/16
./scripts/smoke_test.sh
```

Expected Docker network:

```text
198.18.254.0/28 gateway=198.18.254.1
```

The final `ip -4 route show 172.20.0.0/16` must not display a Docker bridge route. A legitimate VPN route may be visible only when the host itself has a configured VPN route; it must never reference `br-...` or `facerec-internal`.
