function [next1,next2,counts,observation_count,commits,selected,commit] = adc_update(k1,k2,g1,g2,p1,p2,d1,d2,y1,y2,n,mode,mu1,mu2)
%#codegen
% Window accumulators only; visible coefficient memory is in Unit Delays.
persistent sums gate_counts observations commit_count
if isempty(sums)
    sums = zeros(1,8);
    gate_counts = zeros(1,8);
    observations = 0;
    commit_count = 0;
end
next1=k1;
next2=k2;
selected=0;
commit=0;
position=mod(n,120);
if mode == 2
    selected=1;
elseif mode == 3
    selected=double(position < 4);
elseif mode == 4
    selected=1;
end
if selected == 1
    observations=observations+1;
    gate_counts=gate_counts+[g1 g2];
    if mode == 2
        for j=1:4
            if g1(j) == 1
                next1(j)=min(max(k1(j)-mu1(j)*d1*y1,0),2);
            end
            if g2(j) == 1
                next2(j)=min(max(k2(j)-mu2(j)*d2*y2,0),2);
            end
        end
        commit=1;
    else
        sums=sums+[p1 p2];
    end
end
if (mode == 3 || mode == 4) && position == 119
    if mode == 3
        number=4;
        multiplier=30;
    else
        number=120;
        multiplier=1;
    end
    for j=1:4
        % Same order as original update_block_mean(adapted mu).
        next1(j)=min(max(k1(j)-(mu1(j)*multiplier*number)*(sums(j)/number),0),2);
        next2(j)=min(max(k2(j)-(mu2(j)*multiplier*number)*(sums(j+4)/number),0),2);
    end
    sums=zeros(1,8);
    commit=1;
end
commit_count=commit_count+commit;
counts=gate_counts;
observation_count=observations;
commits=commit_count;
end
