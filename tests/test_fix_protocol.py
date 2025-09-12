"""
Test demonstrating FIX Protocol functionality

This test shows:
1. Normal message flow with sequence tracking
2. Gap detection and retransmission
3. Out-of-order message buffering
4. Duplicate message handling
"""

import asyncio
import pytest
from src.core.protocol.fix_protocol import FIXProtocol, SequenceStatus


class TestFIXProtocol:
    """Test the FIX protocol implementation"""
    
    @pytest.fixture
    def setup_protocols(self):
        """Set up two protocol instances simulating adapter and connectome"""
        sent_messages = {"adapter": [], "connectome": []}
        processed_messages = {"adapter": [], "connectome": []}
        
        # Adapter side protocol
        async def adapter_send(event_type, data):
            sent_messages["adapter"].append((event_type, data))
            # Simulate sending to connectome
            if event_type == "protocol_message":
                await connectome_protocol.handle_incoming_message("adapter", data)
            elif event_type == "resend_request":
                await connectome_protocol.handle_resend_request("adapter", data)
                
        async def adapter_process(message_type, body):
            processed_messages["adapter"].append((message_type, body))
            
        adapter_protocol = FIXProtocol(
            node_id="adapter-test",
            send_callback=adapter_send,
            process_callback=adapter_process,
            storage_ttl=60
        )
        
        # Connectome side protocol
        async def connectome_send(event_type, data):
            sent_messages["connectome"].append((event_type, data))
            # Simulate sending to adapter
            if event_type == "protocol_message":
                await adapter_protocol.handle_incoming_message("connectome", data)
            elif event_type == "resend_request":
                await adapter_protocol.handle_resend_request("connectome", data)
                
        async def connectome_process(message_type, body):
            processed_messages["connectome"].append((message_type, body))
            
        connectome_protocol = FIXProtocol(
            node_id="connectome-test",
            send_callback=connectome_send,
            process_callback=connectome_process,
            storage_ttl=60
        )
        
        return {
            "adapter": adapter_protocol,
            "connectome": connectome_protocol,
            "sent": sent_messages,
            "processed": processed_messages
        }
    
    @pytest.mark.asyncio
    async def test_normal_message_flow(self, setup_protocols):
        """Test normal message flow with correct sequencing"""
        protocols = setup_protocols
        adapter = protocols["adapter"]
        connectome = protocols["connectome"]
        processed = protocols["processed"]
        
        # Send messages from adapter to connectome
        await adapter.send_message("bot_request", {"text": "Hello"})
        await adapter.send_message("bot_request", {"text": "World"})
        
        # Check sequences
        assert adapter.outbound_sequence == 2
        assert adapter.get_or_create_peer_state("connectome").last_received == 0
        
        # Check connectome received them
        assert connectome.get_or_create_peer_state("adapter").last_received == 2
        assert len(processed["connectome"]) == 2
        assert processed["connectome"][0] == ("bot_request", {"text": "Hello"})
        assert processed["connectome"][1] == ("bot_request", {"text": "World"})
        
        # Send response from connectome to adapter
        await connectome.send_message("bot_response", {"response": "Hi there!"})
        
        # Check adapter received it
        assert adapter.get_or_create_peer_state("connectome").last_received == 1
        assert len(processed["adapter"]) == 1
        assert processed["adapter"][0] == ("bot_response", {"response": "Hi there!"})
        
    @pytest.mark.asyncio
    async def test_gap_detection_and_retransmission(self, setup_protocols):
        """Test gap detection and automatic retransmission"""
        protocols = setup_protocols
        adapter = protocols["adapter"]
        connectome = protocols["connectome"]
        processed = protocols["processed"]
        sent = protocols["sent"]
        
        # Send seq 1
        await adapter.send_message("bot_request", {"seq": 1})
        assert len(processed["connectome"]) == 1
        
        # Simulate seq 2 being lost by sending seq 3 directly
        adapter.outbound_sequence = 2  # Skip seq 2
        await adapter.send_message("bot_request", {"seq": 3})
        
        # Connectome should detect gap and request retransmission
        # Check that resend request was sent
        resend_requests = [msg for event, msg in sent["connectome"] if event == "resend_request"]
        assert len(resend_requests) == 1
        assert resend_requests[0]["from_sequence"] == 2
        assert resend_requests[0]["to_sequence"] == 2
        
        # Seq 3 should be buffered, not processed yet
        assert len(processed["connectome"]) == 1  # Only seq 1 processed
        peer_state = connectome.get_or_create_peer_state("adapter")
        assert 3 in peer_state.out_of_order_buffer
        
        # Now send the missing seq 2
        adapter.outbound_sequence = 1  # Reset to send seq 2
        await adapter.send_message("bot_request", {"seq": 2})
        
        # Both seq 2 and buffered seq 3 should now be processed
        assert len(processed["connectome"]) == 3
        assert processed["connectome"][1] == ("bot_request", {"seq": 2})
        assert processed["connectome"][2] == ("bot_request", {"seq": 3})
        assert len(peer_state.out_of_order_buffer) == 0
        
    @pytest.mark.asyncio
    async def test_duplicate_message_handling(self, setup_protocols):
        """Test that duplicate messages are ignored"""
        protocols = setup_protocols
        adapter = protocols["adapter"]
        connectome = protocols["connectome"]
        processed = protocols["processed"]
        
        # Send a message
        await adapter.send_message("bot_request", {"id": "msg1"})
        assert len(processed["connectome"]) == 1
        
        # Manually resend the same sequence
        message = adapter.message_storage[1]
        await connectome.handle_incoming_message("adapter", message.to_dict())
        
        # Should not be processed again
        assert len(processed["connectome"]) == 1
        
    @pytest.mark.asyncio
    async def test_sequence_sync_on_connect(self, setup_protocols):
        """Test sequence synchronization when peers connect"""
        protocols = setup_protocols
        adapter = protocols["adapter"]
        connectome = protocols["connectome"]
        
        # Simulate some messages have been exchanged
        adapter.outbound_sequence = 10
        adapter.get_or_create_peer_state("connectome").last_received = 5
        connectome.outbound_sequence = 5
        connectome.get_or_create_peer_state("adapter").last_received = 8
        
        # Connectome connects and sends sync
        sync_data = await connectome.handle_sequence_sync("adapter", {
            "my_outbound_seq": 5,
            "expecting_inbound_seq": 9
        })
        
        # Adapter should detect it's missing messages from connectome
        assert sync_data["my_outbound_seq"] == 5
        assert sync_data["expecting_inbound_seq"] == 9
        
        # Now adapter syncs
        adapter_sync = await adapter.handle_sequence_sync("connectome", sync_data)
        assert adapter_sync["my_outbound_seq"] == 10
        assert adapter_sync["expecting_inbound_seq"] == 6
        
    @pytest.mark.asyncio
    async def test_message_storage_cleanup(self, setup_protocols):
        """Test that old messages are cleaned up"""
        protocols = setup_protocols
        adapter = protocols["adapter"]
        
        # Set short TTL for testing
        adapter.storage_ttl = 0.1  # 100ms
        
        # Send a message
        await adapter.send_message("bot_request", {"test": "cleanup"})
        assert len(adapter.message_storage) == 1
        
        # Wait for cleanup
        await asyncio.sleep(0.2)
        
        # Manually trigger cleanup (normally runs in background)
        await adapter._cleanup_old_messages()
        
        # Message should be gone
        assert len(adapter.message_storage) == 0
        
        # Cleanup the task
        await adapter.shutdown()


if __name__ == "__main__":
    # Run a simple demonstration
    async def demo():
        print("FIX Protocol Demo")
        print("=================")
        
        # Create test instance
        test = TestFIXProtocol()
        protocols = test.setup_protocols()
        
        print("\n1. Normal flow:")
        await test.test_normal_message_flow(protocols)
        print("✓ Messages delivered in order")
        
        print("\n2. Gap detection:")
        protocols = test.setup_protocols()  # Fresh start
        await test.test_gap_detection_and_retransmission(protocols)
        print("✓ Missing messages detected and retransmitted")
        
        print("\n3. Duplicate handling:")
        protocols = test.setup_protocols()  # Fresh start
        await test.test_duplicate_message_handling(protocols)
        print("✓ Duplicates ignored")
        
        print("\nProtocol guarantees:")
        print("- No silent message loss")
        print("- Ordered delivery")
        print("- Automatic recovery from failures")
        
    asyncio.run(demo()) 