import numpy as np
from tqdm import tqdm
import ROOT
import os
from array import array
from time import time
from python.plot import plot_ratio2
from python.apply_corrections import step1, step2


def get_res_correction(
        ntuples_gen,
        pull_bins, r_bins, abseta_bins, nl_bins, pt_bins,
        pdir , hdir,
        do_plot,
        weight
    ):

    ROOT.gROOT.SetBatch(1)
    ROOT.RooMsgService.instance().setGlobalKillBelow(ROOT.RooFit.ERROR)
    ROOT.RooMsgService.instance().setSilentMode(True)

    if do_plot:
        pdir = pdir+'resolution/'
        os.makedirs(pdir, exist_ok=True)
        os.makedirs(pdir+'CB_fits_new/', exist_ok=True)
        os.makedirs(pdir+'pol_fits_new/', exist_ok=True)
    
    #read data
    df = ROOT.RDataFrame("Events", ntuples_gen)
    df = df.Define("bs_weight", "(int)(poisson())")
    df = df.Define("weight", weight)
    df = step1(df, hdir, 'GEN')

    df = df.Define("abseta_1", "abs(eta_1)")
    df = df.Define("abseta_2", "abs(eta_2)")
    df = df.Define("R_1", "genpt_1/pt_1_step1")
    df = df.Define("R_2", "genpt_2/pt_2_step1")

    df = df.Filter(
        "abseta_1 < 2.4 && abseta_2 < 2.4 &&\
        nTrkLayers_1 > 6.5 && nTrkLayers_1 < 17.5 && \
        nTrkLayers_2 > 6.5 && nTrkLayers_2 < 17.5"
    )

    # histogram for means and sigmas to create pull distribution
    mean_hist = ROOT.TH2D(
        'mean_hist', '',
        len(abseta_bins)-1, array('d', abseta_bins),
        len(nl_bins)-1, array('d', nl_bins)
    )

    h_3d_r1 = df.Histo3D(
        (
            "h_3d_r", "",
            len(abseta_bins)-1, array('d', abseta_bins),
            len(nl_bins)-1, array('d', nl_bins),
            len(r_bins)-1, array('d', r_bins)
        ),
        "abseta_1",
        "nTrkLayers_1",
        "R_1",
        "weight"
    )

    h_3d_r2 = df.Histo3D(
        (
            "h_3d_r2", "",
            len(abseta_bins)-1, array('d', abseta_bins),
            len(nl_bins)-1, array('d', nl_bins),
            len(r_bins)-1, array('d', r_bins)
        ),
        "abseta_2",
        "nTrkLayers_2",
        "R_2",
        "weight"
    )

    for eta in range(len(abseta_bins)-1):
        for nl in range(len(nl_bins)-1):
            h_tmp = h_3d_r1.ProjectionZ(
                f"h_tmp_{eta}_{nl}", eta+1, eta+1, nl+1, nl+1
            )
            h_tmp_2 = h_3d_r2.ProjectionZ(
                f"h_tmp_{eta}_{nl}", eta+1, eta+1, nl+1, nl+1
            )
            h_tmp.Add(h_tmp_2)
            mean = h_tmp.GetMean()
            std = h_tmp.GetStdDev()

            mean_hist.SetBinContent(eta+1, nl+1, mean)
            mean_hist.SetBinError(eta+1, nl+1, std)

    tf = ROOT.TFile(f'{hdir}step2_mean_sigma.root', 'recreate')
    mean_hist.Write()
    tf.Close()
    
    # application of mean and sigma to create pull distributions
    ROOT.gROOT.ProcessLine(f'TFile* tf = TFile::Open("{hdir}step2_mean_sigma.root", "read");')
    ROOT.gROOT.ProcessLine(f'TH2D* mean_hist = (TH2D*)tf->Get("mean_hist");')

    df = df.Define(
        "pull_1",
        'double pull1;\
        Int_t etabin_1 = mean_hist->GetXaxis()->FindBin(abseta_1);\
        Int_t nlbin_1 = mean_hist->GetYaxis()->FindBin(nTrkLayers_1);\
        double sigma_1 = mean_hist->GetBinError(etabin_1, nlbin_1);\
        pull1 = (R_1 - mean_hist->GetBinContent(etabin_1, nlbin_1)) / sigma_1;\
        return pull1;'
    )
    df = df.Define(
        "pull_2",
        'double pull2;\
        Int_t etabin_2 = mean_hist->GetXaxis()->FindBin(abseta_2);\
        Int_t nlbin_2 = mean_hist->GetYaxis()->FindBin(nTrkLayers_2);\
        double sigma_2 = mean_hist->GetBinError(etabin_2, nlbin_2);\
        pull2 = (R_2 - mean_hist->GetBinContent(etabin_2, nlbin_2)) / sigma_2;\
        return pull2;'
    )

    h_3d_pull1 = df.Histo3D(
        (
            "h_3d_pull1", "",
            len(abseta_bins)-1, array('d', abseta_bins),
            len(nl_bins)-1, array('d', nl_bins),
            len(pull_bins)-1, array('d', pull_bins)
        ),
        "abseta_1",
        "nTrkLayers_1",
        "pull_1",
        "weight"
    )
    h_3d_pull2 = df.Histo3D(
        (
            "h_3d_pull2", "",
            len(abseta_bins)-1, array('d', abseta_bins),
            len(nl_bins)-1, array('d', nl_bins),
            len(pull_bins)-1, array('d', pull_bins)
        ),
        "abseta_2",
        "nTrkLayers_2",
        "pull_2",
        "weight"
    )

    h_3d_pull1.Sumw2()
    h_3d_pull2.Sumw2()

    # Definiton of histograms for the fit results
    h_results_cb = ROOT.TH3D(
        'h_results_cb', '', 
        len(abseta_bins)-1, array('d', abseta_bins),
        len(nl_bins)-1, array('d', nl_bins),
        4, array('d', [0,1,2,3,4])
    )
    h_results_poly = ROOT.TH3D(
        'h_results_poly', '',
        len(abseta_bins)-1, array('d', abseta_bins),
        len(nl_bins)-1, array('d', nl_bins),
        3, array('d', [0,1,2,3])
    )

    for eta in range(len(abseta_bins)-1):

        df_tmp_1 = df.Filter(f"abseta_1 > {abseta_bins[eta]} && abseta_1 < {abseta_bins[eta+1]}")
        df_tmp_2 = df.Filter(f"abseta_2 > {abseta_bins[eta]} && abseta_2 < {abseta_bins[eta+1]}")

        # pt binned histogram for extraction of sigmas for poly-fits
        h_3d_r_poly1 = df_tmp_1.Histo3D(
            (
                'h_3d_r_poly', '',
                len(nl_bins)-1, array('d', nl_bins),
                len(pt_bins)-1, array('d', pt_bins), 
                len(r_bins)-1, array('d', r_bins),
            ),
            "nTrkLayers_1",
            "genpt_1",
            "R_1",
            "weight"
        )

        h_3d_r_poly2 = df_tmp_1.Histo3D(
            (
                'h_3d_r_poly2', '',
                len(nl_bins)-1, array('d', nl_bins),
                len(pt_bins)-1, array('d', pt_bins), 
                len(r_bins)-1, array('d', r_bins),
            ),
            "nTrkLayers_1",
            "genpt_1",
            "R_1",
            "weight"
        )

        for nl in range(len(nl_bins)-1):
            
            # perform CB fits in bins of abseta and nl
            h_tmp = h_3d_pull1.ProjectionZ('_pz', eta+1, eta+1, nl+1, nl+1)
            h_tmp2 = h_3d_pull2.ProjectionZ('_pz', eta+1, eta+1, nl+1, nl+1)

            h_tmp.Add(h_tmp2)

            if h_tmp.Integral() == 0:
                continue

            h_tmp.Scale(1./h_tmp.Integral())

            x = ROOT.RooRealVar("x", "pull", -5, 5)
            x.setBins(10000,"cache")
            x.setMin("cache", -10)
            x.setMax("cache", 10)

            mean = ROOT.RooRealVar("mean", "mean", 0, -1, 1)
            sigma = ROOT.RooRealVar("sigma", "sigma", h_tmp.GetStdDev(), 0, 5)
            n = ROOT.RooRealVar("n", "n", 10, 0, 1000)
            alpha = ROOT.RooRealVar("alpha", "alpha", 1, 0, 5)
            cb = ROOT.RooCrystalBall("cb", "CrystalBall", x, mean, sigma,
                                                sigma, alpha, n, alpha, n)
            roohist = ROOT.RooDataHist("hist", "", ROOT.RooArgSet(x), h_tmp)
            fitResult = cb.fitTo(
                roohist,
                ROOT.RooFit.AsymptoticError(True),
                ROOT.RooFit.PrintEvalErrors(-1)
            )

            h_results_cb.SetBinContent(eta+1, nl+1, 1, mean.getVal())
            h_results_cb.SetBinError(eta+1, nl+1, 1, mean.getError())
            h_results_cb.SetBinContent(eta+1, nl+1, 2, sigma.getVal())
            h_results_cb.SetBinError(eta+1, nl+1, 2, sigma.getError())
            h_results_cb.SetBinContent(eta+1, nl+1, 3, n.getVal())
            h_results_cb.SetBinError(eta+1, nl+1, 3, n.getError())
            h_results_cb.SetBinContent(eta+1, nl+1, 4, alpha.getVal())
            h_results_cb.SetBinError(eta+1, nl+1, 4, alpha.getError())
                
            if do_plot:
                # Create a canvas for plotting
                c1 = ROOT.TCanvas("c1", "Fitted Histogram", 800, 600)
                frame = x.frame()
                roohist.plotOn(
                    frame, 
                    ROOT.RooFit.DrawOption("B"), 
                    ROOT.RooFit.FillStyle(0), 
                    ROOT.RooFit.FillColor(ROOT.kBlue)
                )
                cb.plotOn(frame, ROOT.RooFit.LineColor(ROOT.kBlue))
                frame.Draw()

                # Display the canvas
                c1.Update()
                c1.Modified()

                cmsTex=ROOT.TLatex()
                cmsTex.SetTextFont(42)
                cmsTex.SetTextSize(0.025)
                cmsTex.SetNDC()
                cmsTex.DrawLatex(0.2,0.85,f'Mean: {round(mean.getVal(),2)} #pm {round(mean.getError(), 2)}')
                cmsTex.DrawLatex(0.2,0.8,f'Sigma: {round(sigma.getVal(),2)} #pm {round(sigma.getError(), 2)}')

                # Optionally, save the plot as an image
                c1.SaveAs(f"./{pdir}CB_fits_new/eta{eta}_nL{nl}.png")
                c1.Clear()

            sigma_hist = ROOT.TH1D('sigma_hist', '', len(pt_bins)-1, array('d', pt_bins))

            for pt in range(len(pt_bins)-1):
                h_tmp_pt = h_3d_r_poly1.ProjectionZ('h_pt_pz', nl+1, nl+1, pt+1, pt+1)
                h_tmp_pt2 = h_3d_r_poly2.ProjectionZ('h_pt_pz', nl+1, nl+1, pt+1, pt+1)

                h_tmp_pt.Add(h_tmp_pt2)

                if h_tmp_pt.GetEntries() > 1:
                    std = h_tmp_pt.GetStdDev()
                    std_err = std / (2 * h_tmp_pt.GetEntries() - 2)**.5

                    sigma_hist.SetBinContent(pt+1, std)
                    sigma_hist.SetBinError(pt+1, std_err)

            # Define the second-order polynomial function
            polynomial = ROOT.TF1("polynomial", "[0] + [1]*x + [2]*x*x")

            # Set initial parameter values and fit
            polynomial.SetParameter(0, 0.01)  # Coefficient for the constant term
            polynomial.SetParameter(1, 5e-5)   # Coefficient for the linear term
            polynomial.SetParameter(2, 5e-5)   # Coefficient for the quadratic term

            sigma_hist.Fit("polynomial")

            for i in range(3):
                h_results_poly.SetBinContent(eta+1, nl+1, i+1, polynomial.GetParameter(i))
                h_results_poly.SetBinError(eta+1, nl+1, i+1, polynomial.GetParError(i))
            
            if do_plot:
            # Create a canvas for plotting
                c1 = ROOT.TCanvas("c1", "Fitted Histogram", 800, 600)

                # Plot the histogram
                sigma_hist.SetMarkerStyle(ROOT.kFullCircle)
                sigma_hist.Draw("ep")
                sigma_hist.SetStats(0)
                sigma_hist.GetXaxis().SetTitle('pT (GeV)')
                sigma_hist.GetYaxis().SetTitle('#sigma (R)')
                sigma_hist.GetYaxis().SetTitleOffset(1.5)
                c1.SetLeftMargin(.1)

                # Plot the fitted function
                polynomial.SetLineColor(ROOT.kRed)  # Set the color to red
                polynomial.Draw("same")

                # Optionally, save the plot as an image
                c1.SaveAs(f"./{pdir}pol_fits_new/eta{eta}_nL{nl}.png")
                c1.Clear()

    tf = ROOT.TFile(f'{hdir}step2_fitresults.root', 'recreate')
    h_results_cb.Write()
    h_results_poly.Write()
    tf.Close()




def plot_closure(ntuples_gen, hdir, pdir, weight):
    use_CB_smear=True
    pdir = pdir+'resolution/'
    
    # application of mean and sigma to create pull distributions
    ROOT.gROOT.ProcessLine(f'TFile* tf = TFile::Open("{hdir}step2_fitresults.root", "read");')
    ROOT.gROOT.ProcessLine(f'TH3D* h_results_cb = (TH3D*)tf->Get("h_results_cb");')
    ROOT.gROOT.ProcessLine(f'TH3D* h_results_poly = (TH3D*)tf->Get("h_results_poly");')
    #ROOT.gROOT.ProcessLine('tf->Close()')

    df = ROOT.RDataFrame("Events", ntuples_gen)
    df = df.Define("bs_weight", "(int)(poisson())")
    df = df.Define("weight", weight)
    df = step1(df, hdir, 'GEN')
    df = step2(df, hdir, 'GEN')

    m_bins = np.linspace(60, 120, 60)

    hists = [
        df.Histo1D(
            (
                'h_gen', '',
                len(m_bins)-1, array('d', m_bins)
            ),
            'genmass_Z',
            "weight"
        ),
        df.Histo1D(
            (
                'h_gen_smeared', '',
                len(m_bins)-1, array('d', m_bins)
            ),
            'genmass_Z_step2',
            "weight"
        ),
        df.Histo1D(
            (
                'h_mc', '',
                len(m_bins)-1, array('d', m_bins)
            ),
            'mass_Z_step2',
            "weight"
        ),
    ]

    m_bins = np.linspace(86, 96, 60)

    hists += [
        df.Histo1D(
            (
                'h_gen_zoom', '',
                len(m_bins)-1, array('d', m_bins)
            ),
            'genmass_Z',
            "weight"
        ),
        df.Histo1D(
            (
                'h_gen_smeared_zoom', '',
                len(m_bins)-1, array('d', m_bins)
            ),
            'genmass_Z_step2',
            "weight"
        ),
        df.Histo1D(
            (
                'h_mc_zoom', '',
                len(m_bins)-1, array('d', m_bins)
            ),
            'mass_Z_step2',
            "weight"
        )
    ]

    tf = ROOT.TFile(f'{hdir}step2_closure.root', 'recreate')
    for h in hists:
        h.Write()
    tf.Close()

    tf = ROOT.TFile(f'{hdir}step2_closure.root', 'read')
    h_gen =  tf.Get('h_gen')
    h_gen.Sumw2()
    h_gen.Scale(1./h_gen.Integral())

    h_mc = tf.Get('h_mc')
    h_mc.Sumw2()
    h_mc.Scale(1./h_mc.Integral())

    h_gensm = tf.Get('h_gen_smeared')
    h_gensm.Sumw2()
    h_gensm.Scale(1./h_gensm.Integral())

    plot_ratio2(
        hists={
            'gen': h_gen,
            'mc': h_mc,
            'gen_smeared': h_gensm
        }, 
        title='',
        outfile=f'{pdir}Z_mass_comparison',
        text=['','',''],
        #xrange=[60, 120],
        labels={
            'gen': 'Generated mass',
            'mc': 'reconstructed Mass',
            'gen_smeared': 'smeared Gen Mass'
        }
    )
    plot_ratio2(
        hists={
            'gen': tf.Get('h_gen_zoom'),
            'mc': tf.Get('h_mc_zoom'),
            'gen_smeared': tf.Get('h_gen_smeared_zoom')
        }, 
        title='',
        outfile=f'{pdir}Z_mass_comparison_zoom',
        text=['','',''],
        #xrange=[86, 96],
        ratio_range=[0.9, 1.1],
        labels={
            'gen': 'Generated mass',
            'mc': 'reconstructed Mass',
            'gen_smeared': 'smeared Gen Mass'
        }
    )