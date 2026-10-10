"""Offline inverse-gain positive control on the already declared grid."""

import argparse
import json
from pathlib import Path

import numpy as np

from experiments.exp_057_static_two_stage_million.common import (
    basis,corrected_arrays,plant_arrays,write)


def audit(folder):
    protocol=json.loads((folder/"protocol.json").read_text(encoding="utf-8-sig"))
    n=protocol["validation_points"]
    x=np.repeat(-.82+(np.arange(n)+.5)*(1.64/n),4)
    tags=np.tile(np.array([[-1,-1],[-1,1],[1,-1],[1,1]]),(n,1))
    rows=[]
    for case in protocol["cases"]:
        if case["stage1"][1] or case["stage2"][1]:continue
        raw=plant_arrays(x,tags[:,0],tags[:,1],case)
        a1,a2=case["stage1"][0],case["stage2"][0]
        k=np.array([1/a1]*4+[1/a2]*4)
        output,y1,y2,r1=corrected_arrays(raw[0],raw[1],raw[4],tags[:,0],tags[:,1],k)
        e1=x-raw[0]/4
        e2=raw[2]-raw[1]/4
        identity=max(float(np.max(np.abs(y1-2048*e1))),float(np.max(np.abs(y2-512*e2))))
        t1,t2=256/a1,64/a2
        # Additional frozen control: only the front third/fourth slopes stay
        # at unity while the rear remains the correct inverse.
        partial=k.copy();partial[2:4]=1
        _,partial_y1,_,partial_r1=corrected_arrays(raw[0],raw[1],raw[4],tags[:,0],tags[:,1],partial)
        row={"case":case["name"],"grid_observations":len(x),"backend":"continuous reference",
            "maximum_inverse_local_identity_error_codes":identity,
            "front_local_magnitude_max":float(np.max(np.abs(y1))),
            "rear_local_magnitude_max":float(np.max(np.abs(y2))),
            "front_third_threshold":t1,"rear_third_threshold":t2,
            "front_third_gates_at_inverse":int(np.count_nonzero(np.abs(y1)>=t1)),
            "rear_third_gates_at_inverse":int(np.count_nonzero(np.abs(y2)>=t2)),
            "front_third_nonzero_basis_at_inverse":int(np.count_nonzero(basis(r1,128)[:,2])),
            "rear_third_nonzero_basis_at_inverse":int(np.count_nonzero(basis(raw[4],32)[:,2])),
            "front_third_gates_with_unlearned_high_slopes":int(np.count_nonzero(np.abs(partial_y1)>=t1)),
            "front_third_nonzero_basis_with_unlearned_high_slopes":int(np.count_nonzero(basis(partial_r1,128)[:,2])),
            "partial_front_validation_mse":float(np.mean((512*raw[0]+basis(partial_r1,128)@partial[:4]-64*tags[:,0]-2048*x)**2)),
            "training_not_changed":True,"oracle_not_fed_to_learner":True}
        assert identity<1e-9
        assert row["front_third_gates_at_inverse"]==row["rear_third_gates_at_inverse"]==0
        assert row["front_third_gates_with_unlearned_high_slopes"]==0
        assert row["front_third_nonzero_basis_with_unlearned_high_slopes"]>0
        rows.append(row)
    write(folder/"support_bound_audit.json",{"rows":rows,"positive_control_only":True,
        "same_predeclared_validation_grid":True,"new_training":False,"chip_geometry_certified":False})
    print(json.dumps(rows,indent=2))


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("folder",type=Path)
    audit(p.parse_args().folder.resolve())
