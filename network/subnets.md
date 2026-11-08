# Subnetting and Network Access Control Documentation

## 1. Subnet Allocation

### Requirements
We are given the base network block `10.20.0.0/16`.
The subnets must be allocated in order from the largest requirement to the smallest, placing each subnet immediately after the previous one, using the smallest prefix (tightest CIDR block) that satisfies the host requirements.

| Subnet Name | Hosts Needed | Calculation (Usable Hosts: $2^{32-\text{prefix}} - 2$) | Prefix Length | Total Capacity | Usable Hosts |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **app** | 1,000 | $2^{10} - 2 = 1024 - 2 = 1022 \ge 1000$ | `/22` | 1024 | 1022 |
| **public** | 250 | $2^{8} - 2 = 256 - 2 = 254 \ge 250$ | `/24` | 256 | 254 |
| **data** | 100 | $2^{7} - 2 = 128 - 2 = 126 \ge 100$ | `/25` | 128 | 126 |
| **management** | 20 | $2^{5} - 2 = 32 - 2 = 30 \ge 20$ | `/27` | 32 | 30 |

---

### Step-by-Step Allocation & Working

1. **app Subnet**:
   - Starting Address: `10.20.0.0`
   - Prefix: `/22` ($32 - 10 = 22$, subnet mask `255.255.252.0`)
   - Size: $2^{10} = 1024$ IP addresses
   - Address Range: `10.20.0.0` to `10.20.3.255`
   - Network Address: `10.20.0.0`
   - Usable Host Range: `10.20.0.1` – `10.20.3.254`
   - Broadcast Address: `10.20.3.255`
   - Usable Hosts: $1022$

2. **public Subnet**:
   - Placed directly after `app`: `10.20.4.0`
   - Prefix: `/24` ($32 - 8 = 24$, subnet mask `255.255.255.0`)
   - Size: $2^{8} = 256$ IP addresses
   - Address Range: `10.20.4.0` to `10.20.4.255`
   - Network Address: `10.20.4.0`
   - Usable Host Range: `10.20.4.1` – `10.20.4.254`
   - Broadcast Address: `10.20.4.255`
   - Usable Hosts: $254$

3. **data Subnet**:
   - Placed directly after `public`: `10.20.5.0`
   - Prefix: `/25` ($32 - 7 = 25$, subnet mask `255.255.255.128`)
   - Size: $2^{7} = 128$ IP addresses
   - Address Range: `10.20.5.0` to `10.20.5.127`
   - Network Address: `10.20.5.0`
   - Usable Host Range: `10.20.5.1` – `10.20.5.126`
   - Broadcast Address: `10.20.5.127`
   - Usable Hosts: $126$

4. **management Subnet**:
   - Placed directly after `data`: `10.20.5.128`
   - Prefix: `/27` ($32 - 5 = 27$, subnet mask `255.255.255.224`)
   - Size: $2^{5} = 32$ IP addresses
   - Address Range: `10.20.5.128` to `10.20.5.159`
   - Network Address: `10.20.5.128`
   - Usable Host Range: `10.20.5.129` – `10.20.5.158`
   - Broadcast Address: `10.20.5.159`
   - Usable Hosts: $30$

---

### Final Subnet Table

| Subnet | Network Address | Prefix Length | Usable Host Range | Broadcast Address | Number of Usable Hosts |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **app** | `10.20.0.0` | `/22` | `10.20.0.1` – `10.20.3.254` | `10.20.3.255` | 1022 |
| **public** | `10.20.4.0` | `/24` | `10.20.4.1` – `10.20.4.254` | `10.20.4.255` | 254 |
| **data** | `10.20.5.0` | `/25` | `10.20.5.1` – `10.20.5.126` | `10.20.5.127` | 126 |
| **management** | `10.20.5.128` | `/27` | `10.20.5.129` – `10.20.5.158` | `10.20.5.159` | 30 |

---

## 2. NACL Architecture and Reasoning

### Stateless Nature of Network Access Control Lists (NACLs)
Unlike stateful firewalls (such as security groups) that maintain connection state tracking tables, a Network Access Control List (NACL) is **completely stateless**. A stateless filter evaluates each packet in complete isolation according to its headers (source IP, destination IP, protocol, source port, destination port) without any historical context or awareness of connection state (such as TCP SYN, ACK, or established handshakes).

Consequently:
1. When a client initiates an inbound request to a web server (e.g. from an ephemeral port to port 80/443), the inbound rule allows the incoming request packet.
2. However, the server's response packet travels in the opposite direction (outbound) with the client's original ephemeral port (1024–65535) as the destination port.
3. Because the NACL does not remember that this outbound packet is part of an already-approved inbound session, the outbound traffic will be blocked by default unless there is an explicit outbound rule permitting return traffic to ephemeral ports `1024–65535`.
4. Similarly, when the public load balancer initiates outbound traffic to the backend application servers on TCP port 8000, the application servers' return response packets arrive back at the public subnet as inbound packets targeting ephemeral ports `1024–65535`. Without an explicit inbound rule permitting reply packets from the app subnet (`10.20.0.0/22`), the return traffic would be dropped, breaking all communication.

### Importance of Rule Ordering for `198.51.100.0/24`
NACL rules are processed sequentially in ascending numerical order (lowest rule number first), and evaluation terminates on the **first matching rule** (first-match wins). If no rule matches, the default deny rule (at rule `*` / 32767) is triggered.

Because `198.51.100.0/24` is a subset of `0.0.0.0/0` (anywhere):
- If the explicit DENY rule for `198.51.100.0/24` were placed with a rule number higher than the ALLOW rule for TCP 80/443 from `0.0.0.0/0`, inbound web traffic originating from `198.51.100.0/24` would hit the general ALLOW rule first and be admitted.
- To enforce blocking of all traffic from `198.51.100.0/24`—even on web ports 80 and 443—the DENY rule must be assigned a lower rule number than the broad `0.0.0.0/0` allow rules. This guarantees that any packet with a source IP within `198.51.100.0/24` matches the DENY rule immediately and is dropped before reaching the subsequent allow rules.

