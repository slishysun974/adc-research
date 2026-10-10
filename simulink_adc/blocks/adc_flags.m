function flags = adc_flags(x,aux1,r1,aux2,r2,raw_unclipped,corrected_unclipped)
%#codegen
% Every overload/clipping event is retained; auxiliary alone loses no data.
flags=zeros(1,17);
flags(1)=double(x < -1); flags(2)=double(x >= 1);
flags(3)=double(aux1 < -1); flags(4)=double(aux1 >= 1);
flags(5)=double(r1 < -1); flags(6)=double(r1 >= 1);
flags(7)=double(aux2 < -1); flags(8)=double(aux2 >= 1);
flags(9)=double(r2 < -1); flags(10)=double(r2 >= 1);
flags(11)=double(raw_unclipped < 0); flags(12)=double(raw_unclipped > 4095);
flags(13)=double(corrected_unclipped < 0); flags(14)=double(corrected_unclipped > 4095);
physical=any(flags([1 2 5 6 9 10]));
flags(15)=double(~physical && ~any(flags(11:12)));
flags(16)=double(~any(flags(13:14)));
flags(17)=double(~physical && ~any(flags(13:14)));
end
