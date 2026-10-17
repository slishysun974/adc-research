using System;
using System.IO;
using System.Collections.Generic;

// Experiment-local scheduling only. Readout/commit remain the frozen069 code.
public static class Adc070 {
    public sealed class PathSpec {
        public string Name,Rate,Variant,Method;
        public int Num,Den,Selected,Multiplier;
        public int[] Initial;
    }
    public sealed class Result {
        public int Windows,Conversions; public long GlobalStart;
        public PathSpec[] Paths; public Adc069.Block[] Blocks;
        public long[] CoefficientClips,OutputClips;
    }
    public static int[] LastState(string folder,string stem,string name) {
        using(var input=new BinaryReader(File.OpenRead(Path.Combine(folder,stem+"_"+name+"_q22.bin")))) {
            input.BaseStream.Seek(-32,SeekOrigin.End);
            var a=new int[8];for(int j=0;j<8;j++)a[j]=input.ReadInt32();return a;
        }
    }
    public static Result Run(string folder,string stem,string wordFile,int wordStart,int windows,long globalStart,PathSpec[] specs) {
        int paths=specs.Length;var ctx=new Adc059.Context[paths];var states=new BinaryWriter[paths];
        var nz=new long[paths][];var z0=new long[paths][];var nz0=new long[paths][];var h0=new long[paths][];var e0=new long[paths][];
        var blocks=new List<Adc069.Block>();Adc069.Block block=null;
        if(globalStart%120!=0||wordStart<0||windows<=0)throw new Exception("aligned complete windows required");
        for(int h=0;h<paths;h++) {
            var s=specs[h];if(s.Initial.Length!=8||s.Den<=0||s.Num<=0)throw new Exception("initial/rate");
            ctx[h]=new Adc059.Context();nz[h]=new long[8];
            states[h]=new BinaryWriter(File.Open(Path.Combine(folder,stem+"_"+s.Name+"_q22.bin"),FileMode.CreateNew));
            for(int j=0;j<8;j++) {
                if(s.Initial[j]<0||s.Initial[j]>2047*4096)throw new Exception("initial range");
                ctx[h].Acc[j]=s.Initial[j];ctx[h].Hidden[j]=s.Initial[j]/4194304.0;states[h].Write(s.Initial[j]);
            }
        }
        try {
            using(var words=new BinaryReader(File.OpenRead(wordFile)))
            using(var output=new BinaryWriter(File.Open(Path.Combine(folder,stem+"_outputs.bin"),FileMode.CreateNew))) {
                words.BaseStream.Seek(480L*wordStart,SeekOrigin.Begin);
                for(int w=0;w<windows;w++) {
                    if(w%256==0) {
                        block=new Adc069.Block{All=new Adc062.Counts[paths],Selected=new Adc062.Counts[paths],ZeroRequest=new long[paths][],NonzeroSumZero=new long[paths][],HiddenChanged=new long[paths][],ExportChanged=new long[paths][]};
                        for(int h=0;h<paths;h++) {
                            block.All[h]=new Adc062.Counts();block.Selected[h]=new Adc062.Counts();
                            z0[h]=(long[])ctx[h].ZeroRequest.Clone();nz0[h]=(long[])nz[h].Clone();h0[h]=(long[])ctx[h].HiddenChanged.Clone();e0[h]=(long[])ctx[h].ExportChanged.Clone();
                        }
                    }
                    foreach(var c in ctx)c.Begin(3);
                    for(int j=0;j<120;j++) {
                        int q1=words.ReadSByte(),q2=words.ReadSByte(),be=words.ReadSByte(),bits=words.ReadByte();
                        if(bits>3)throw new Exception("tags");int d1=(bits&1)==0?-1:1,d2=(bits&2)==0?-1:1;
                        for(int h=0;h<paths;h++) {
                            var v=Adc059.Correct(q1,q2,be,d1,d2,ctx[h].K,3);
                            output.Write((short)Math.Round(v[0],MidpointRounding.ToEven));
                            Adc062.Accumulate(ctx[h],block.All[h],block.Selected[h],v,be,d1,d2,j<specs[h].Selected);
                        }
                    }
                    for(int h=0;h<paths;h++) {
                        var s=specs[h];Adc069.Commit(ctx[h],s.Multiplier,s.Num,s.Den,nz[h]);
                        foreach(long a in ctx[h].Acc)states[h].Write((int)a);
                    }
                    if(w%256==255||w==windows-1) {
                        for(int h=0;h<paths;h++) {
                            block.ZeroRequest[h]=Adc062.Difference(ctx[h].ZeroRequest,z0[h]);block.NonzeroSumZero[h]=Adc062.Difference(nz[h],nz0[h]);
                            block.HiddenChanged[h]=Adc062.Difference(ctx[h].HiddenChanged,h0[h]);block.ExportChanged[h]=Adc062.Difference(ctx[h].ExportChanged,e0[h]);
                        }
                        blocks.Add(block);
                    }
                }
            }
        } finally {foreach(var s in states)s.Dispose();}
        var clips=new long[paths];var oc=new long[paths];for(int h=0;h<paths;h++){clips[h]=ctx[h].Clips;oc[h]=ctx[h].OutputClips;}
        return new Result{Windows=windows,Conversions=120*windows,GlobalStart=globalStart,Paths=specs,Blocks=blocks.ToArray(),CoefficientClips=clips,OutputClips=oc};
    }
}
