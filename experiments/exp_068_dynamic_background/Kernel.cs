using System;
using System.IO;
using System.Collections.Generic;

// Experiment-local physical acceleration. Digital arithmetic is frozen EXP059/062.
public static class Adc068 {
    public static double[] Plant(double x,int d1,int d2,double a1,double b1,double a2,double b2,
                                 double[] alpha,double beta,double[] h) {
        int q1=Adc057.Flash(x);
        double z1=4*(x-q1/4.0+d1/32.0),t1=a1*z1+b1*Math.Pow(z1,3),ta=t1;
        double sm=beta*h[0],sa=beta*h[1];
        double m=t1+alpha[0]*(sm-t1),aux=ta+alpha[1]*(sa-ta);
        int q2=Adc057.Flash(aux);
        double z2=4*(m-q2/4.0+d2/32.0),t2=a2*z2+b2*Math.Pow(z2,3),s2=beta*h[2];
        double r=t2+alpha[2]*(s2-t2);
        if(x< -1||x>=1||Math.Abs(z1)>1||m< -1||m>=1||Math.Abs(z2)>1||r< -1||r>=1)
            throw new Exception("physical overload/domain");
        h[0]=m;h[1]=aux;h[2]=r;
        return new double[]{q1,q2,Adc057.Quantize(r),z1,z2,sm,sa,s2,t1,ta,t2,m,aux,r};
    }
    public static Adc062.Result Run(string folder,string name,ulong seed,double a1,double b1,double a2,double b2,
                             double[] alpha,double beta,double[] tone,int windows,int[] probeWindows) {
        string stem=Path.Combine(folder,name+"_"+seed);int bw=tone.Length/120;
        var ctx=new Adc059.Context[]{new Adc059.Context(),new Adc059.Context()};
        var unit=new double[]{1,1,1,1,1,1,1,1};var h=new double[3];var keep=new HashSet<int>(probeWindows);
        var blocks=new List<Adc062.Block>();Adc062.Block block=null;long[][] zero=null,hidden=null,exported=null;int probes=0;
        using(var words=new BinaryWriter(File.Open(stem+"_words.bin",FileMode.CreateNew)))
        using(var codes=new BinaryWriter(File.Open(stem+"_outputs.bin",FileMode.CreateNew)))
        using(var p=new BinaryWriter(File.Open(stem+"_point30_q22.bin",FileMode.CreateNew)))
        using(var f=new BinaryWriter(File.Open(stem+"_full120_q22.bin",FileMode.CreateNew)))
        using(var history=new BinaryWriter(File.Open(stem+"_history.bin",FileMode.CreateNew)))
        using(var audit=new BinaryWriter(File.Open(stem+"_probes.bin",FileMode.CreateNew))) {
            var states=new BinaryWriter[]{p,f};foreach(var s in states)foreach(double k in unit)s.Write(k);
            foreach(double v in h)history.Write(v);
            for(int w=0;w<windows;w++) {
                if(w%bw==0) {
                    block=new Adc062.Block{Selected=new Adc062.Counts[]{new Adc062.Counts(),new Adc062.Counts()},
                        All=new Adc062.Counts[]{new Adc062.Counts(),new Adc062.Counts()},
                        ZeroRequest=new long[2][],HiddenChanged=new long[2][],ExportChanged=new long[2][]};
                    zero=new long[2][];hidden=new long[2][];exported=new long[2][];
                    for(int m=0;m<2;m++){zero[m]=(long[])ctx[m].ZeroRequest.Clone();hidden[m]=(long[])ctx[m].HiddenChanged.Clone();exported[m]=(long[])ctx[m].ExportChanged.Clone();}
                }
                foreach(var c in ctx)c.Begin(3);bool save=keep.Contains(w);
                if(save){audit.Write((double)w);foreach(double v in h)audit.Write(v);foreach(var c in ctx)foreach(double k in c.Hidden)audit.Write(k);probes++;}
                for(int j=0;j<120;j++) {
                    long index=120L*w+j;double x=tone[index%tone.Length];
                    int d1=Adc057.Tag(seed,2,index),d2=Adc057.Tag(seed,3,index);
                    var raw=Plant(x,d1,d2,a1,b1,a2,b2,alpha,beta,h);
                    int q1=(int)raw[0],q2=(int)raw[1],be=(int)raw[2];
                    words.Write((sbyte)q1);words.Write((sbyte)q2);words.Write((sbyte)be);words.Write((byte)((d1>0?1:0)|(d2>0?2:0)));
                    codes.Write((short)Math.Round(Adc059.Correct(q1,q2,be,d1,d2,unit,3)[0],MidpointRounding.ToEven));
                    for(int m=0;m<2;m++) {
                        var value=Adc059.Correct(q1,q2,be,d1,d2,ctx[m].K,3);
                        codes.Write((short)Math.Round(value[0],MidpointRounding.ToEven));
                        Adc062.Accumulate(ctx[m],block.All[m],block.Selected[m],value,be,d1,d2,m==1||j<4);
                    }
                    if(save){audit.Write(x);audit.Write((double)d1);audit.Write((double)d2);foreach(double v in raw)audit.Write(v);}
                }
                foreach(double v in h)history.Write(v);
                if(save)foreach(var c in ctx)foreach(double s in c.Sums)audit.Write(s);
                for(int m=0;m<2;m++){Adc059.Commit(ctx[m],3,m==0?30:1);foreach(double k in ctx[m].Hidden)states[m].Write(k);}
                if(save)foreach(var c in ctx)foreach(double k in c.Hidden)audit.Write(k);
                if(w%bw==bw-1||w==windows-1) {
                    for(int m=0;m<2;m++){block.ZeroRequest[m]=Adc062.Difference(ctx[m].ZeroRequest,zero[m]);block.HiddenChanged[m]=Adc062.Difference(ctx[m].HiddenChanged,hidden[m]);block.ExportChanged[m]=Adc062.Difference(ctx[m].ExportChanged,exported[m]);}
                    blocks.Add(block);
                }
            }
        }
        return new Adc062.Result{Windows=windows,Conversions=120*windows,ProbeWindows=probes,Blocks=blocks.ToArray(),
            CoefficientClips=new long[]{ctx[0].Clips,ctx[1].Clips},OutputClips=new long[]{ctx[0].OutputClips,ctx[1].OutputClips}};
    }
}
