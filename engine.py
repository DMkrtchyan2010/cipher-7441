import random
import base64
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator

def run_bb84_simulation(num_photons=32, intercept_rate_eve1=0.0, intercept_rate_eve2=0.0, threshold=0.11):
    sim = AerSimulator()
    alice_bits = [random.randint(0, 1) for _ in range(num_photons)]
    alice_bases = [random.choice(['Z', 'X']) for _ in range(num_photons)]
    bob_bases = [random.choice(['Z', 'X']) for _ in range(num_photons)]
    
    photon_logs = []
    sifted_alice = []
    sifted_bob = []
    errors = 0
    matches = 0
    
    eve1_count = 0
    eve2_count = 0
    
    for i in range(num_photons):
        qc = QuantumCircuit(1, 1)
        
        # Alice preparation & polarization mapping
        if alice_bases[i] == 'Z':
            if alice_bits[i] == 1: qc.x(0)
            polarization = "0° / 90° (Rectilinear)" if alice_bits[i] == 0 else "90° (Rectilinear)"
        else:
            if alice_bits[i] == 0: qc.h(0)
            else: qc.x(0); qc.h(0)
            polarization = "+45° (Diagonal)" if alice_bits[i] == 0 else "-45° (Diagonal)"
            
        # --- EVE-1 INTERCEPTION (Hacker 1) ---
        eve1_intercepted = random.random() < intercept_rate_eve1
        eve1_action = "BYPASSED"
        eve1_guessed_bit = None
        
        if eve1_intercepted:
            eve1_count += 1
            eve1_basis = random.choice(['Z', 'X'])
            if eve1_basis == 'X': qc.h(0)
            qc.measure(0, 0)
            job1 = sim.run(qc, shots=1, memory=True)
            eve1_guessed_bit = int(job1.result().get_memory()[0])
            eve1_action = f"INTERCEPTED (Eve1: {eve1_basis}-basis)"
            
            # Re-prepare qubit downstream based on Eve-1's measurement
            qc = QuantumCircuit(1, 1)
            if eve1_basis == 'Z':
                if eve1_guessed_bit == 1: qc.x(0)
            else:
                if eve1_guessed_bit == 0: qc.h(0)
                else: qc.x(0); qc.h(0)

        # --- EVE-2 INTERCEPTION (Hacker 2 - Multi-hacker mesh) ---
        eve2_intercepted = random.random() < intercept_rate_eve2
        eve2_action = "BYPASSED"
        eve2_guessed_bit = None
        
        if eve2_intercepted:
            eve2_count += 1
            eve2_basis = random.choice(['Z', 'X'])
            if eve2_basis == 'X': qc.h(0)
            qc.measure(0, 0)
            job2 = sim.run(qc, shots=1, memory=True)
            eve2_guessed_bit = int(job2.result().get_memory()[0])
            eve2_action = f"INTERCEPTED (Eve2: {eve2_basis}-basis)"
            
            # Re-prepare qubit downstream based on Eve-2's measurement
            qc = QuantumCircuit(1, 1)
            if eve2_basis == 'Z':
                if eve2_guessed_bit == 1: qc.x(0)
            else:
                if eve2_guessed_bit == 0: qc.h(0)
                else: qc.x(0); qc.h(0)

        # --- BOB MEASUREMENT ---
        if bob_bases[i] == 'X': qc.h(0)
        qc.measure(0, 0)
        
        job = sim.run(qc, shots=1, memory=True)
        measured_bit = int(job.result().get_memory()[0])
        
        matched = (alice_bases[i] == bob_bases[i])
        error = False
        if matched:
            matches += 1
            sifted_alice.append(alice_bits[i])
            sifted_bob.append(measured_bit)
            if alice_bits[i] != measured_bit:
                errors += 1
                error = True
                
        combined_eve_action = eve1_action
        if eve2_intercepted:
            combined_eve_action += f" -> {eve2_action}"

        photon_logs.append({
            "id": i + 1,
            "alice_bit": alice_bits[i],
            "alice_basis": alice_bases[i],
            "polarization": polarization,
            "eve1_intercepted": eve1_intercepted,
            "eve2_intercepted": eve2_intercepted,
            "eve_action": combined_eve_action,
            "bob_basis": bob_bases[i],
            "bob_bit": measured_bit,
            "matched": matched,
            "error": error
        })
            
    qber = (errors / matches) if matches > 0 else 0.0
    qber_percent = round(qber * 100, 2)
    
    # Dynamic Security Check vs Adjustable Threshold (e.g., default 11% -> 0.11)
    secure = qber_percent <= (threshold * 100)
    
    if secure and len(sifted_alice) >= 8:
        raw_key_bytes = bytes([int("".join(map(str, sifted_alice[i:i+8])), 2) for i in range(0, len(sifted_alice) - 7, 8)])
        derived_key = base64.b64encode(raw_key_bytes[:16]).decode('utf-8')
    else:
        derived_key = "PURGED_BY_DECOHERENCE_OR_BREACH"
    
    return {
        "num_photons": num_photons,
        "intercept_rate_eve1": intercept_rate_eve1,
        "intercept_rate_eve2": intercept_rate_eve2,
        "threshold": threshold,
        "sifted_matches": matches,
        "errors": errors,
        "qber": qber_percent,
        "secure": secure,
        "derived_key": derived_key,
        "eve1_total_intercepts": eve1_count,
        "eve2_total_intercepts": eve2_count,
        "photon_logs": photon_logs
    }