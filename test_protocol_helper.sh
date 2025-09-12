#!/bin/bash
# Protocol Test Helper Script

echo "=== Protocol Test Helper ==="
echo

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check protocol state
check_state() {
    echo -e "${YELLOW}Current Protocol State:${NC}"
    if [ -d "./protocol_state" ]; then
        echo "Adapter state:"
        cat ./protocol_state/adapter-*_state.json 2>/dev/null | jq '.' || echo "No adapter state found"
        echo
        echo "Message count:"
        for f in ./protocol_state/*_messages.json; do
            if [ -f "$f" ]; then
                count=$(cat "$f" | jq 'keys | length')
                echo "  $(basename $f): $count messages"
            fi
        done
    else
        echo "No protocol state directory found"
    fi
    echo
}

# Function to monitor logs
monitor_protocol() {
    echo -e "${YELLOW}Monitoring protocol activity (Ctrl+C to stop):${NC}"
    tail -f *.log | grep -E --color=always "sequence|Sequence|Gap detected|resend|retransmit|Protocol"
}

# Function to clean state
clean_state() {
    echo -e "${RED}Cleaning protocol state...${NC}"
    rm -rf ./protocol_state/
    echo "Protocol state cleaned"
    echo
}

# Function to backup state
backup_state() {
    if [ -d "./protocol_state" ]; then
        backup_name="protocol_state_backup_$(date +%Y%m%d_%H%M%S)"
        cp -r ./protocol_state/ "./$backup_name"
        echo -e "${GREEN}State backed up to: $backup_name${NC}"
    else
        echo "No state to backup"
    fi
    echo
}

# Function to simulate sequence gap
create_gap() {
    echo -e "${YELLOW}Creating artificial sequence gap...${NC}"
    # This would need to be customized based on your setup
    echo "Edit the state file to increment sequence by 5"
    echo "Then send a message to trigger gap detection"
    echo
}

# Main menu
case "$1" in
    "state")
        check_state
        ;;
    "monitor")
        monitor_protocol
        ;;
    "clean")
        read -p "Are you sure you want to clean protocol state? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            clean_state
        fi
        ;;
    "backup")
        backup_state
        ;;
    "gap")
        create_gap
        ;;
    "test-persistence")
        echo -e "${YELLOW}Testing persistence...${NC}"
        check_state
        echo "Sending test marker message..."
        echo "CHECK STATE AGAIN AFTER RESTART"
        ;;
    "health")
        echo -e "${YELLOW}Protocol Health Check:${NC}"
        echo
        echo "Recent sequences:"
        grep -E "sequence.*[0-9]+" *.log | tail -5
        echo
        echo "Recent gaps:"
        grep "Gap detected" *.log | tail -5 || echo "No gaps detected (good!)"
        echo
        echo "Recent resends:"
        grep -i "resend" *.log | tail -5 || echo "No resends (good!)"
        echo
        ;;
    *)
        echo "Usage: $0 {state|monitor|clean|backup|gap|test-persistence|health}"
        echo
        echo "  state           - Show current protocol state"
        echo "  monitor         - Live monitor protocol logs"
        echo "  clean           - Clean protocol state (careful!)"
        echo "  backup          - Backup current state"
        echo "  gap             - Instructions to create sequence gap"
        echo "  test-persistence - Check persistence is working"
        echo "  health          - Quick protocol health check"
        echo
        ;;
esac 