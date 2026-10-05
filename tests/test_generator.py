import sys, os, collections
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backend.case_generator.generator import generate_case, Gen
from backend.agents import case_director
from backend.agents.common import View
from backend.agents import evidence_analyst as ea, hypothesis_analyst as ha

def run(n=40):
    stats = collections.Counter(); attempts = collections.Counter(); fails = []
    for diff in ["EASY","MEDIUM","HARD","EXPERT"]:
        for i in range(n):
            seed = "%04X-%04X" % (i*977+13, i*131+7)
            try:
                b = generate_case(seed, diff)
            except Exception as e:
                import traceback; traceback.print_exc(); fails.append((diff, seed, repr(e))); continue
            ok,_ = case_director.validate(b)
            stats[(diff, ok)] += 1
            attempts[diff] += b["case"]["data"].get("attempt", 99)
    print(dict(stats)); print("avg attempts", {k: v/n for k,v in attempts.items()}); print("fails", fails[:3])
if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv)>1 else 30)
