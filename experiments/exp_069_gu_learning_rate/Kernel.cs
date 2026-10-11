using System;
using System.IO;
using System.Collections.Generic;

// Experiment-local learner acceleration; source ADC words are read-only.
public static class Adc069 {
    public sealed class Rate { public string Name; public int Num,Den; }
    public sealed class Block {
        public Adc062.Counts[] All,Selected;
        public long[][] ZeroRequest,NonzeroSumZero,HiddenChanged,ExportChanged;
    }
    public sealed class Result {
        public int Windows,Conversions; public string[] Paths;
        public Block[] Blocks; public long[] CoefficientClips,OutputClips;
        public long[] BaselineCodesChecked,BaselineStatesChecked;
    }
    public static void Commit(Adc059.Context c,int multiplier,int num,int den,long[] nonzeroSumZero) {
        int[] weights={1,3,6,12};
        for(int j=0;j<8;j++) {
            if(c.Sums[j]!=(long)c.Sums[j])throw new Exception("noninteger product");
            long before=c.Acc[j],sum=(long)c.Sums[j];
            long delta=Adc059.Rn((j<4?-2L:-32L)*weights[j%4]*multiplier*num*sum,125L*den);
            if(delta==0){c.ZeroRequest[j]++;if(sum!=0)nonzeroSumZero[j]++;}
            long next=before+delta;if(next<0||next>2047L*4096)c.Clips++;
            c.Acc[j]=Math.Min(2047L*4096,Math.Max(0,next));c.Hidden[j]=c.Acc[j]/4194304.0;
            if(before!=c.Acc[j])c.HiddenChanged[j]++;
            if(Adc059.Rn(c.Acc[j],4096)/1024.0!=c.K[j])c.ExportChanged[j]++;
            c.Sums[j]=0;
        }
    }
    public static Result Run(string folder,string source,string stem,int windows,Rate[] rates,bool checkBase) {
        int paths=rates.Length*2,bw=256;var ctx=new Adc059.Context[paths];var names=new string[paths];
        var state=new BinaryWriter[paths];var nonzero=new long[paths][];
        var oldZero=new long[paths][];var oldNonzero=new long[paths][];var oldHidden=new long[paths][];var oldExport=new long[paths][];
        var baseCodes=new long[paths];var baseStates=new long[paths];
        var reference=new BinaryReader[]{null,null};
        for(int h=0;h<paths;h++) {
            ctx[h]=new Adc059.Context();nonzero[h]=new long[8];names[h]=rates[h/2].Name+"_"+(h%2==0?"point30":"full120");
            state[h]=new BinaryWriter(File.Open(Path.Combine(folder,stem+"_"+names[h]+"_q22.bin"),FileMode.CreateNew));
            foreach(long v in ctx[h].Acc)state[h].Write((int)v);
        }
        if(checkBase)for(int m=0;m<2;m++) {
            reference[m]=new BinaryReader(File.OpenRead(Path.Combine(source,stem+(m==0?"_point30":"_full120")+"_q22.bin")));
            for(int j=0;j<8;j++)if(reference[m].ReadDouble()!=1.0)throw new Exception("source initial");
        }
        var blocks=new List<Block>();Block block=null;
        try {
            using(var words=new BinaryReader(File.OpenRead(Path.Combine(source,stem+"_words.bin"))))
            using(var baseline=new BinaryReader(File.OpenRead(Path.Combine(source,stem+"_outputs.bin"))))
            using(var output=new BinaryWriter(File.Open(Path.Combine(folder,stem+"_outputs.bin"),FileMode.CreateNew))) {
                for(int w=0;w<windows;w++) {
                    if(w%bw==0) {
                        block=new Block{All=new Adc062.Counts[paths],Selected=new Adc062.Counts[paths],ZeroRequest=new long[paths][],NonzeroSumZero=new long[paths][],HiddenChanged=new long[paths][],ExportChanged=new long[paths][]};
                        for(int h=0;h<paths;h++) {
                            block.All[h]=new Adc062.Counts();block.Selected[h]=new Adc062.Counts();
                            oldZero[h]=(long[])ctx[h].ZeroRequest.Clone();oldNonzero[h]=(long[])nonzero[h].Clone();
                            oldHidden[h]=(long[])ctx[h].HiddenChanged.Clone();oldExport[h]=(long[])ctx[h].ExportChanged.Clone();
                        }
                    }
                    foreach(var c in ctx)c.Begin(3);
                    for(int j=0;j<120;j++) {
                        int q1=words.ReadSByte(),q2=words.ReadSByte(),be=words.ReadSByte(),bits=words.ReadByte();
                        if(bits>3)throw new Exception("source tags");int d1=(bits&1)==0?-1:1,d2=(bits&2)==0?-1:1;
                        short unit=baseline.ReadInt16(),bp=baseline.ReadInt16(),bf=baseline.ReadInt16();
                        for(int h=0;h<paths;h++) {
                            var value=Adc059.Correct(q1,q2,be,d1,d2,ctx[h].K,3);
                            short code=(short)Math.Round(value[0],MidpointRounding.ToEven);output.Write(code);
                            Adc062.Accumulate(ctx[h],block.All[h],block.Selected[h],value,be,d1,d2,h%2==1||j<4);
                            if(checkBase&&rates[h/2].Num==rates[h/2].Den) {
                                if(code!=(h%2==0?bp:bf))throw new Exception("base code mismatch");baseCodes[h]++;
                            }
                        }
                    }
                    for(int h=0;h<paths;h++) {
                        var rate=rates[h/2];Commit(ctx[h],h%2==0?30:1,rate.Num,rate.Den,nonzero[h]);
                        foreach(long value in ctx[h].Acc)state[h].Write((int)value);
                        if(checkBase&&rate.Num==rate.Den)for(int j=0;j<8;j++) {
                            if(reference[h%2].ReadDouble()!=ctx[h].Hidden[j])throw new Exception("base state mismatch");baseStates[h]++;
                        }
                    }
                    if(w%bw==bw-1||w==windows-1) {
                        for(int h=0;h<paths;h++) {
                            block.ZeroRequest[h]=Adc062.Difference(ctx[h].ZeroRequest,oldZero[h]);
                            block.NonzeroSumZero[h]=Adc062.Difference(nonzero[h],oldNonzero[h]);
                            block.HiddenChanged[h]=Adc062.Difference(ctx[h].HiddenChanged,oldHidden[h]);
                            block.ExportChanged[h]=Adc062.Difference(ctx[h].ExportChanged,oldExport[h]);
                        }
                        blocks.Add(block);
                    }
                }
            }
        } finally {foreach(var s in state)s.Dispose();foreach(var s in reference)if(s!=null)s.Dispose();}
        var clips=new long[paths];var outputClips=new long[paths];for(int h=0;h<paths;h++){clips[h]=ctx[h].Clips;outputClips[h]=ctx[h].OutputClips;}
        return new Result{Windows=windows,Conversions=120*windows,Paths=names,Blocks=blocks.ToArray(),CoefficientClips=clips,OutputClips=outputClips,
                          BaselineCodesChecked=baseCodes,BaselineStatesChecked=baseStates};
    }
}
