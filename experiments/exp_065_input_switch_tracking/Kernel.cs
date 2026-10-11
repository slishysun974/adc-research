using System;
using System.IO;
using System.Collections.Generic;

// Experiment-local source and bookkeeping. Frozen EXP059 digital readout/commit.
public static class Adc065 {
    public sealed class Counts {
        public long[] Gates=new long[8],Basis=new long[8],Both=new long[8],Correlations=new long[8];
    }
    public sealed class Block {
        public Counts[] Selected,All;
        public long[][] ZeroRequest,HiddenChanged,ExportChanged;
    }
    public sealed class Result {
        public int Windows,Conversions,ProbeWindows; public long StartIndex,SwitchIndex;
        public Block[] Blocks;
        public long[] CoefficientClips,OutputClips;
    }
    // No analog data, input, target, or score enters this function.
    public static void Accumulate(Adc059.Context c,Counts all,Counts selected,double[] value,int be,int d1,int d2,bool learn) {
        if(value[0]<0||value[0]>4095)c.OutputClips++;
        for(int bank=0;bank<2;bank++) {
            double width=bank==0?128:32,local=value[bank+1],mag=Math.Abs(bank==0?value[3]:be),sum=0;
            long product=(long)((bank==0?64*d1:16*d2)*local);
            for(int j=0;j<4;j++) {
                int h=4*bank+j;bool g=j==0||Math.Abs(local)>=Adc059.Q3(width*sum),b=mag>j*width;
                if(g){all.Gates[h]++;all.Correlations[h]+=product;}
                if(b)all.Basis[h]++;if(g&&b)all.Both[h]++;
                if(learn) {
                    if(g){c.Sums[h]+=product;c.Gates[h]++;selected.Gates[h]++;selected.Correlations[h]+=product;}
                    if(b){c.Basis[h]++;selected.Basis[h]++;}
                    if(g&&b){c.Both[h]++;selected.Both[h]++;}
                }
                sum+=c.K[h];
            }
        }
    }
    public static long[] Difference(long[] after,long[] before) {
        var r=new long[8];for(int j=0;j<8;j++)r[j]=after[j]-before[j];return r;
    }
    public static Result Run(string folder,string name,ulong seed,double a1,double b1,double a2,double b2,
                             double[] tone,int windows,int[] probeWindows,long startIndex,long switchIndex,double scale,double[][] initial) {
        string stem=Path.Combine(folder,name+"_"+seed);int blockWindows=tone.Length/120;
        var ctx=new Adc059.Context[]{new Adc059.Context(),new Adc059.Context()};
        if(startIndex<0||startIndex%120!=0||switchIndex%120!=0)throw new Exception("window boundary required");
        for(int m=0;m<2;m++)for(int j=0;j<8;j++) {
            double a=initial[m][j]*4194304;
            if(a!=Math.Round(a)||a<0||a>2047L*4096)throw new Exception("illegal initial Q22");
            ctx[m].Acc[j]=(long)a;ctx[m].Hidden[j]=initial[m][j];
        }
        var unit=new double[]{1,1,1,1,1,1,1,1};var keep=new HashSet<int>(probeWindows);
        var blocks=new List<Block>();Block block=null;long[][] zero=null,hidden=null,exported=null;int probes=0;
        using(var rawOut=new BinaryWriter(File.Open(stem+"_words.bin",FileMode.CreateNew)))
        using(var codes=new BinaryWriter(File.Open(stem+"_outputs.bin",FileMode.CreateNew)))
        using(var p=new BinaryWriter(File.Open(stem+"_point30_q22.bin",FileMode.CreateNew)))
        using(var f=new BinaryWriter(File.Open(stem+"_full120_q22.bin",FileMode.CreateNew)))
        using(var audit=new BinaryWriter(File.Open(stem+"_probes.bin",FileMode.CreateNew))) {
            var states=new BinaryWriter[]{p,f};for(int m=0;m<2;m++)foreach(double v in ctx[m].Hidden)states[m].Write(v);
            for(int w=0;w<windows;w++) {
                if(w%blockWindows==0) {
                    block=new Block{Selected=new Counts[]{new Counts(),new Counts()},All=new Counts[]{new Counts(),new Counts()},
                        ZeroRequest=new long[2][],HiddenChanged=new long[2][],ExportChanged=new long[2][]};
                    zero=new long[2][];hidden=new long[2][];exported=new long[2][];
                    for(int m=0;m<2;m++){zero[m]=(long[])ctx[m].ZeroRequest.Clone();hidden[m]=(long[])ctx[m].HiddenChanged.Clone();exported[m]=(long[])ctx[m].ExportChanged.Clone();}
                }
                foreach(var c in ctx)c.Begin(3);bool save=keep.Contains(w);
                if(save){audit.Write((double)w);foreach(var c in ctx)foreach(double k in c.Hidden)audit.Write(k);probes++;}
                for(int j=0;j<120;j++) {
                    long index=startIndex+120L*w+j;double x=tone[index%tone.Length]*(index>=switchIndex?scale:1.0);
                    int d1=Adc057.Tag(seed,2,index),d2=Adc057.Tag(seed,3,index);
                    var raw=Adc061.Plant(x,d1,d2,a1,b1,a1,b1,a2,b2);
                    int q1=(int)raw[0],q2=(int)raw[1],be=(int)raw[7];
                    rawOut.Write((sbyte)q1);rawOut.Write((sbyte)q2);rawOut.Write((sbyte)be);rawOut.Write((byte)((d1>0?1:0)|(d2>0?2:0)));
                    codes.Write((short)Math.Round(Adc059.Correct(q1,q2,be,d1,d2,unit,3)[0],MidpointRounding.ToEven));
                    for(int m=0;m<2;m++) {
                        var value=Adc059.Correct(q1,q2,be,d1,d2,ctx[m].K,3);
                        codes.Write((short)Math.Round(value[0],MidpointRounding.ToEven));
                        Accumulate(ctx[m],block.All[m],block.Selected[m],value,be,d1,d2,m==1||j<4);
                    }
                    if(save){audit.Write(x);audit.Write((double)d1);audit.Write((double)d2);foreach(double v in raw)audit.Write(v);}
                }
                if(save)foreach(var c in ctx)foreach(double s in c.Sums)audit.Write(s);
                for(int m=0;m<2;m++){Adc059.Commit(ctx[m],3,m==0?30:1);foreach(double k in ctx[m].Hidden)states[m].Write(k);}
                if(save)foreach(var c in ctx)foreach(double k in c.Hidden)audit.Write(k);
                if(w%blockWindows==blockWindows-1||w==windows-1) {
                    for(int m=0;m<2;m++){block.ZeroRequest[m]=Difference(ctx[m].ZeroRequest,zero[m]);block.HiddenChanged[m]=Difference(ctx[m].HiddenChanged,hidden[m]);block.ExportChanged[m]=Difference(ctx[m].ExportChanged,exported[m]);}
                    blocks.Add(block);
                }
            }
        }
        return new Result{StartIndex=startIndex,SwitchIndex=switchIndex,Windows=windows,Conversions=120*windows,ProbeWindows=probes,Blocks=blocks.ToArray(),
            CoefficientClips=new long[]{ctx[0].Clips,ctx[1].Clips},OutputClips=new long[]{ctx[0].OutputClips,ctx[1].OutputClips}};
    }
}
